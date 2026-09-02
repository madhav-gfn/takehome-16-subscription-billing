"""Overdue invoice alerts (Goal 10)."""

from django.db import transaction
from django.utils import timezone

from src.accounts.models import Role

from ..enums import InvoiceStatus
from ..errors import NotOverdue
from ..models import AlertDismissal
from ..querysets import active_alerts, visible_invoices


def list_alerts(user, today=None):
    today = today or timezone.localdate()
    invoices = (
        active_alerts(user, today)
        .select_related("subscription", "subscription__owner")
        .order_by("due_date")
    )
    # Ruling A-11: only a billing admin can dismiss. Sent to the client so it
    # does not render a button guaranteed to 403.
    dismissible = user.role == Role.BILLING_ADMIN

    return [
        {
            "invoice_id": str(invoice.id),
            "subscription_id": str(invoice.subscription_id),
            "customer_name": invoice.subscription.customer_name,
            "billing_email": invoice.subscription.billing_email,
            "owner_email": invoice.subscription.owner.email,
            "amount": str(invoice.amount),
            "due_date": invoice.due_date,
            "days_overdue": (today - invoice.due_date).days,
            "dismissible": dismissible,
        }
        for invoice in invoices
    ]


def count_alerts(user, today=None):
    # Same queryset as list_alerts, so the nav badge cannot disagree with the
    # list it links to.
    return active_alerts(user, today).count()


@transaction.atomic
def dismiss(invoice_id, user, today=None):
    today = today or timezone.localdate()
    invoice = visible_invoices(user).select_for_update().get(pk=invoice_id)

    if not (
        invoice.status == InvoiceStatus.ISSUED and invoice.due_date < today
    ):
        raise NotOverdue()

    # Record the due date this dismissal was made against. That value is the
    # entire A-10 re-arming mechanism: change the due date and the dismissal
    # stops matching, so once the new date passes the alert returns.
    AlertDismissal.objects.update_or_create(
        invoice=invoice,
        defaults={
            "dismissed_for_due_date": invoice.due_date,
            "dismissed_by": user,
            "dismissed_at": timezone.now(),
        },
    )
    # Deliberately no invoice_event: dismissal is about an operator's own
    # attention, not a fact about the invoice, and Goal 9's timeline should
    # stay about the invoice.
    return invoice
