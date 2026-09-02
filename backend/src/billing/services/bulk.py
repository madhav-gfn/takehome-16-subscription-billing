"""Bulk generation of the current period's invoices (Goal 7)."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..errors import DomainError
from ..models import Invoice, Subscription
from ..periods import current_period, due_date_for
from . import invoices as invoice_service


def bulk_generate(actor, as_of=None):
    """Generate the current period's invoice for every active subscription.

    Returns Goal 7's per-subscription report: generated / skipped / failed,
    with every non-generated row carrying a reason a human can act on.
    """
    as_of = as_of or timezone.localdate()
    subscriptions = (
        Subscription.objects.filter(archived_at__isnull=True)  # Goal 2 / I-14
        .select_related("owner")
        .order_by("customer_name")
    )

    results = [_generate_one(sub, as_of, actor) for sub in subscriptions]

    summary = {"total": len(results)}
    for outcome in ("generated", "skipped", "failed"):
        summary[outcome] = sum(1 for r in results if r["outcome"] == outcome)

    return {"as_of": as_of, "summary": summary, "results": results}


def _generate_one(subscription, as_of, actor):
    row = {
        "subscription_id": str(subscription.id),
        "customer_name": subscription.customer_name,
    }

    period = current_period(
        subscription.start_date, subscription.billing_cycle, as_of
    )
    if period is None:
        # Ruling A-13: nothing went wrong, so this is a skip, not a failure.
        return {
            **row,
            "outcome": "skipped",
            "reason": (
                f"Subscription has not started "
                f"(starts {subscription.start_date})"
            ),
        }

    period_start, period_end = period
    existing = (
        Invoice.objects.filter(
            subscription=subscription,
            period_start=period_start,
            period_end=period_end,
        )
        .exclude(status="void")  # ruling A-14: a void frees the period
        .first()
    )
    if existing:
        return {
            **row,
            "outcome": "skipped",
            "reason": (
                f"An invoice already exists for {period_start} - {period_end}"
            ),
            "invoice_id": str(existing.id),
        }

    try:
        # Savepoint per subscription. One failure must not roll back the run —
        # an all-or-nothing bulk action turns one bad row into a wasted pass
        # and tells the operator nothing about the others.
        with transaction.atomic():
            invoice = invoice_service.create_invoice(
                subscription=subscription,
                period_start=period_start,
                period_end=period_end,
                amount=subscription.price,
                due_date=due_date_for(period_start),
                actor=actor,
                source="bulk",
            )
    except IntegrityError:
        # Lost a race with a concurrent run. Landing on the correct end state
        # is not an error, so it reports the same as any other duplicate.
        return {
            **row,
            "outcome": "skipped",
            "reason": (
                f"An invoice already exists for {period_start} - {period_end}"
            ),
        }
    except DomainError as exc:
        return {**row, "outcome": "failed", "reason": exc.message}
    except Exception as exc:  # noqa: BLE001 - the report must survive anything
        return {**row, "outcome": "failed", "reason": str(exc)}

    return {
        **row,
        "outcome": "generated",
        "invoice_id": str(invoice.id),
        "period_start": period_start,
        "period_end": period_end,
        "amount": str(invoice.amount),
    }
