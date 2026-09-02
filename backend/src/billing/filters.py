"""Server-side filtering for Goal 6.

Every filter here resolves to SQL. Nothing reaches the browser unfiltered.
"""

import django_filters as df
from django.db.models import Q
from django.utils import timezone

from .enums import InvoiceStatus
from .models import Invoice, Subscription


class InvoiceFilterSet(df.FilterSet):
    search = df.CharFilter(method="filter_search")
    status = df.MultipleChoiceFilter(
        field_name="status", choices=InvoiceStatus.choices
    )
    overdue = df.BooleanFilter(method="filter_overdue")
    owner = df.UUIDFilter(field_name="subscription__owner_id")
    subscription = df.UUIDFilter(field_name="subscription_id")
    due_before = df.DateFilter(field_name="due_date", lookup_expr="lte")
    due_after = df.DateFilter(field_name="due_date", lookup_expr="gte")

    class Meta:
        model = Invoice
        fields = []

    def filter_search(self, qs, name, value):
        value = (value or "").strip()
        if not value:
            return qs
        return qs.filter(
            Q(subscription__customer_name__icontains=value)
            | Q(subscription__billing_email__icontains=value)
        )

    def filter_overdue(self, qs, name, value):
        if value is None:
            return qs
        today = timezone.localdate()
        condition = Q(status=InvoiceStatus.ISSUED, due_date__lt=today)
        return qs.filter(condition) if value else qs.exclude(condition)


# ?ordering=<key> -> ORM ordering. `status` maps to the annotated lifecycle
# order, not the alphabet: draft/issued/paid/void happening to sort correctly
# alphabetically is a coincidence, not a property.
INVOICE_ORDERING = {
    "due_date": ["due_date"],
    "-due_date": ["-due_date"],
    "amount": ["amount"],
    "-amount": ["-amount"],
    "status": ["status_order"],
    "-status": ["-status_order"],
    "created_at": ["created_at"],
    "-created_at": ["-created_at"],
}
DEFAULT_INVOICE_ORDERING = ["-due_date", "-created_at"]

SUBSCRIPTION_ORDERING = {
    "customer_name": ["customer_name"],
    "-customer_name": ["-customer_name"],
    "price": ["price"],
    "-price": ["-price"],
    "start_date": ["start_date"],
    "-start_date": ["-start_date"],
    "created_at": ["created_at"],
    "-created_at": ["-created_at"],
}
DEFAULT_SUBSCRIPTION_ORDERING = ["-created_at"]


class SubscriptionFilterSet(df.FilterSet):
    search = df.CharFilter(method="filter_search")
    archived = df.CharFilter(method="filter_archived")  # true | false | all
    owner = df.UUIDFilter(field_name="owner_id")
    plan = df.CharFilter(field_name="plan_name", lookup_expr="iexact")

    class Meta:
        model = Subscription
        fields = []

    def filter_search(self, qs, name, value):
        value = (value or "").strip()
        if not value:
            return qs
        return qs.filter(
            Q(customer_name__icontains=value)
            | Q(billing_email__icontains=value)
        )

    def filter_archived(self, qs, name, value):
        # Default is applied in the view, not here: a FilterSet only sees
        # params that were actually sent.
        value = (value or "false").lower()
        if value == "all":
            return qs
        return qs.filter(archived_at__isnull=(value != "true"))
