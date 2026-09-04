"""Visibility scoping and the SQL annotations that back it.

These mirror the RLS policies deliberately. The ORM filters are what make the
API behave correctly and stay testable on SQLite; RLS is what makes it true
even if a view forgets its filter. When the two disagree, RLS wins and the
symptom is a missing row — which the RLS test suite exists to catch.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    DecimalField,
    DurationField,
    F,
    IntegerField,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from src.accounts.models import Role

from .enums import STATUS_SORT_ORDER, InvoiceStatus
from .models import Invoice, Subscription


def visible_subscriptions(user):
    qs = Subscription.objects.select_related("owner")
    if user.role == Role.BILLING_ADMIN:
        return qs
    # .distinct() is required — the collaborator join duplicates rows, which
    # would show duplicates in the Goal 5 list and inflate the Goal 6 count.
    return qs.filter(
        Q(owner_id=user.id) | Q(collaborators__user_id=user.id)
    ).distinct()


def visible_invoices(user):
    qs = Invoice.objects.select_related("subscription", "subscription__owner")
    if user.role == Role.BILLING_ADMIN:
        return qs
    return qs.filter(
        Q(subscription__owner_id=user.id)
        | Q(subscription__collaborators__user_id=user.id)
    ).distinct()


def annotate_invoice_flags(qs, today=None):
    """is_overdue / days_overdue / credited_total / status_order, all in SQL.

    The client never derives these. Computing "overdue" in two places is how a
    badge ends up disagreeing with the filter that produced the row.
    """
    today = today or timezone.localdate()
    overdue = Q(status=InvoiceStatus.ISSUED) & Q(due_date__lt=today)
    return qs.annotate(
        is_overdue=Case(
            When(overdue, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        days_overdue=Case(
            When(overdue, then=Value(today) - F("due_date")),
            default=Value(timedelta(0)),
            output_field=DurationField(),
        ),
        credited_total=Coalesce(
            Sum("credit_notes__amount"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        status_order=Case(
            *[
                When(status=status, then=Value(order))
                for status, order in STATUS_SORT_ORDER.items()
            ],
            output_field=IntegerField(),
        ),
    )


def active_alerts(user, today=None):
    """Overdue invoices whose alert is currently showing (Goal 10 / A-10).

    The single definition. Both /api/alerts/ and /api/alerts/count/ call this,
    so the nav badge cannot disagree with the list it links to.

    The exclude is the entire re-arming mechanism: a dismissal suppresses the
    alert only while it still points at the invoice's current due date. Change
    the due date and the dismissal stops matching, so once the new date passes
    the invoice alerts again.
    """
    today = today or timezone.localdate()
    return (
        visible_invoices(user)
        .filter(status=InvoiceStatus.ISSUED, due_date__lt=today)
        .exclude(alert_dismissal__dismissed_for_due_date=F("due_date"))
    )
