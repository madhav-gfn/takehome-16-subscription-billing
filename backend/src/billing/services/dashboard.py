"""Dashboard aggregates (Goal 8).

One query per section rather than one query overall: a six-way outer join to
save five round trips on a page that loads once is the wrong trade.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce, TruncWeek
from django.utils import timezone

from ..enums import InvoiceStatus
from ..models import CreditNote
from ..querysets import visible_invoices

ZERO = Value(
    Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2)
)


def build(user, today=None):
    today = today or timezone.localdate()
    month_start = today.replace(day=1)
    invoices = visible_invoices(user)

    return {
        "as_of": today,
        "headline": _headline(invoices, today, month_start),
        "by_status": _by_status(invoices),
        "by_plan": _by_plan(invoices),
        "revenue_by_week": _revenue_by_week(invoices, today),
    }


def _headline(invoices, today, month_start):
    # Ruling A-08: "issued this month" reads issued_at, not current status. An
    # invoice issued in March and paid in April still counts as issued in March.
    issued = invoices.filter(issued_at__date__gte=month_start).count()

    # Ruling A-09: collected reads paid_at.
    collected = invoices.filter(paid_at__date__gte=month_start).aggregate(
        t=Coalesce(Sum("amount"), ZERO)
    )["t"]

    # Ruling A-06: credits are reported beside revenue, never netted into it.
    # Netting hides exactly the information the spreadsheet workflow lost.
    credits = CreditNote.objects.filter(
        invoice__in=invoices, created_at__date__gte=month_start
    ).aggregate(t=Coalesce(Sum("amount"), ZERO))["t"]

    receivables = invoices.filter(status=InvoiceStatus.ISSUED).aggregate(
        t=Coalesce(Sum("amount"), ZERO)
    )["t"]

    overdue = invoices.filter(
        status=InvoiceStatus.ISSUED, due_date__lt=today
    ).aggregate(n=Count("id"), t=Coalesce(Sum("amount"), ZERO))

    return {
        "invoices_issued_this_month": issued,
        "revenue_collected_this_month": str(collected),
        "credits_issued_this_month": str(credits),
        "receivables": str(receivables),
        "invoices_overdue": overdue["n"],
        "overdue_amount": str(overdue["t"]),
    }


def _by_status(invoices):
    rows = {
        r["status"]: r
        for r in invoices.values("status").annotate(
            count=Count("id"), amount=Coalesce(Sum("amount"), ZERO)
        )
    }
    # Every status, including the empty ones: a breakdown that hides zeros
    # makes the reader guess whether the category exists at all.
    return [
        {
            "status": status.value,
            "count": rows.get(status.value, {}).get("count", 0),
            "amount": str(
                rows.get(status.value, {}).get("amount", Decimal("0.00"))
            ),
        }
        for status in InvoiceStatus
    ]


def _by_plan(invoices):
    rows = (
        invoices.values("subscription__plan_name")
        .annotate(count=Count("id"), amount=Coalesce(Sum("amount"), ZERO))
        .order_by("-amount")
    )
    return [
        {
            "plan_name": r["subscription__plan_name"],
            "count": r["count"],
            "amount": str(r["amount"]),
        }
        for r in rows
    ]


def _revenue_by_week(invoices, today):
    """Exactly 8 buckets, oldest first, zeros included.

    The backend emits the empty weeks so the chart cannot silently rescale its
    own x-axis and mislead.
    """
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=7)

    rows = (
        invoices.filter(paid_at__date__gte=first)
        .annotate(week=TruncWeek("paid_at"))
        .values("week")
        .annotate(amount=Coalesce(Sum("amount"), ZERO))
    )
    found = {}
    for row in rows:
        if row["week"]:
            week = row["week"]
            found[week.date() if hasattr(week, "date") else week] = row["amount"]

    buckets = []
    for i in range(8):
        week_start = first + timedelta(weeks=i)
        buckets.append(
            {
                "week_start": week_start,
                "amount": str(found.get(week_start, Decimal("0.00"))),
            }
        )
    return buckets
