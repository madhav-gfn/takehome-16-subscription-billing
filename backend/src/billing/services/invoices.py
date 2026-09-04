r"""Invoice rules (Goals 3, 4, 9).

Everything that can change an invoice goes through this module. In particular
`transition` is the ONLY function in the codebase that assigns Invoice.status —
that single-writer property is what makes "every status change writes exactly
one event" true by construction rather than by discipline.

Verify with:  grep -rn "\.status = " src/billing/
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from ..enums import ALLOWED_TRANSITIONS, EventType, InvoiceStatus
from ..errors import (
    CreditExceedsInvoice,
    CreditNoteRequiresPaid,
    InvalidTransition,
    InvoiceIssuedLocked,
    InvoicePaidCannotVoid,
    InvoicePaidImmutable,
    InvoiceVoidTerminal,
    PeriodAlreadyInvoiced,
    SubscriptionArchived,
    VoidReasonRequired,
)
from ..models import CreditNote, Invoice, InvoiceEvent

# Which fields may be written, by current status (doc 02 section 3).
EDITABLE_FIELDS = {
    InvoiceStatus.DRAFT: {"period_start", "period_end", "amount", "due_date"},
    # Goal 3: "change its due date until it is Paid" — survives the Goal 4
    # lock on period and amount.
    InvoiceStatus.ISSUED: {"due_date"},
    InvoiceStatus.PAID: set(),
    InvoiceStatus.VOID: set(),
}


def _event(invoice, event_type, actor, *, old_status=None, new_status=None, **details):
    return InvoiceEvent.objects.create(
        invoice=invoice,
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
        actor=actor,
        details=details,
    )


def _reject_immutable(invoice):
    """Raise the right error for a write attempt against a frozen invoice."""
    if invoice.status == InvoiceStatus.PAID:
        raise InvoicePaidImmutable()
    if invoice.status == InvoiceStatus.VOID:
        raise InvoiceVoidTerminal()


@transaction.atomic
def create_invoice(
    *, subscription, period_start, period_end, amount, due_date, actor,
    source="manual",
):
    if subscription.is_archived:
        raise SubscriptionArchived()

    clash = (
        Invoice.objects.filter(
            subscription=subscription,
            period_start=period_start,
            period_end=period_end,
        )
        .exclude(status=InvoiceStatus.VOID)
        .first()
    )
    if clash:
        raise PeriodAlreadyInvoiced(period_start, period_end, clash.id)

    invoice = Invoice.objects.create(
        subscription=subscription,
        period_start=period_start,
        period_end=period_end,
        amount=amount,
        due_date=due_date,
        status=InvoiceStatus.DRAFT,  # nobody creates a non-draft invoice
        created_by=actor,
    )
    _event(
        invoice,
        EventType.CREATED,
        actor,
        amount=str(amount),
        period_start=str(period_start),
        period_end=str(period_end),
        due_date=str(due_date),
        source=source,
    )
    return invoice


@transaction.atomic
def edit_invoice(invoice, *, actor, **changes):
    """Apply field changes permitted by the invoice's current status."""
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        return invoice

    _reject_immutable(invoice)

    allowed = EDITABLE_FIELDS[InvoiceStatus(invoice.status)]
    rejected = set(changes) - allowed
    if rejected:
        # The only remaining case is an issued invoice being sent a locked
        # field; draft allows everything, paid and void raised above.
        raise InvoiceIssuedLocked()

    applied = {}
    for field, value in changes.items():
        old = getattr(invoice, field)
        if old == value:
            continue
        applied[field] = {"from": str(old), "to": str(value)}
        setattr(invoice, field, value)

    if not applied:
        return invoice

    period_start = changes.get("period_start", invoice.period_start)
    period_end = changes.get("period_end", invoice.period_end)
    if period_start > period_end:
        from rest_framework.exceptions import ValidationError

        raise ValidationError(
            {"period_end": "The period end must be on or after the start."}
        )

    invoice.save(update_fields=[*applied.keys(), "updated_at"])
    # One event per request, not one per field: the timeline should read as a
    # list of actions someone took, not a list of column writes.
    _event(invoice, EventType.FIELD_CHANGED, actor, changes=applied)
    return invoice


@transaction.atomic
def transition(invoice, target, actor, *, reason=None):
    """Move an invoice to `target`. The only writer of Invoice.status."""
    # Re-read under a row lock: two concurrent "mark paid" clicks must not both
    # succeed and write two events.
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    current = InvoiceStatus(invoice.status)
    target = InvoiceStatus(target)

    if target not in ALLOWED_TRANSITIONS[current]:
        if current == InvoiceStatus.PAID and target == InvoiceStatus.VOID:
            raise InvoicePaidCannotVoid()
        if current == InvoiceStatus.VOID:
            raise InvoiceVoidTerminal()
        raise InvalidTransition(current.value, target.value)

    fields = ["status", "updated_at"]
    invoice.status = target

    if target == InvoiceStatus.ISSUED:
        invoice.issued_at = timezone.now()
        fields.append("issued_at")
    elif target == InvoiceStatus.PAID:
        invoice.paid_at = timezone.now()
        fields.append("paid_at")
    elif target == InvoiceStatus.VOID:
        if not (reason or "").strip():
            raise VoidReasonRequired()
        invoice.void_reason = reason.strip()
        fields.append("void_reason")

    # update_fields keeps the immutability trigger from seeing spurious diffs.
    invoice.save(update_fields=fields)

    _event(
        invoice,
        EventType.STATUS_CHANGED,
        actor,
        old_status=current.value,
        new_status=target.value,
    )
    if target == InvoiceStatus.VOID:
        # A second event so the reason has a home of its own in the timeline.
        _event(invoice, EventType.VOIDED, actor, reason=invoice.void_reason)

    return invoice


@transaction.atomic
def add_credit_note(invoice, *, amount, reason, actor):
    """Correct a Paid invoice without altering it (Goal 4, rulings A-04/A-05)."""
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != InvoiceStatus.PAID:
        raise CreditNoteRequiresPaid(invoice.status)

    existing = invoice.credit_notes.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
    new_total = existing + amount
    if new_total > invoice.amount:
        raise CreditExceedsInvoice(amount, new_total, invoice.amount)

    credit_note = CreditNote.objects.create(
        invoice=invoice, amount=amount, reason=reason.strip(), created_by=actor
    )
    _event(
        invoice,
        EventType.CREDIT_NOTE_ISSUED,
        actor,
        credit_note_id=str(credit_note.id),
        amount=str(amount),
        reason=credit_note.reason,
    )
    return credit_note


@transaction.atomic
def add_note(invoice, actor, text):
    """A note is an event, not a field — so it is allowed in any state,
    including Paid, without violating immutability (ruling A-18)."""
    return _event(invoice, EventType.NOTE_ADDED, actor, text=text.strip())
