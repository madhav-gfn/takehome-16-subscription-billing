# 14 — Backend Code Scaffolds

Docs 02–06 settle *what* and *why*. This file is the *how*: the skeletons for the files that were
described rather than written. Copy these in and fill the bodies — every signature, every field
list and every query below is decided.

Not repeated here: `db.py` (in [04](04-authorization-matrix.md) §6), the RLS SQL
([04](04-authorization-matrix.md) §4), the triggers ([03](03-database-schema.md) §8), and
`transition()` ([06](06-backend-build-plan.md) Step 6).

---

## 1. `enums.py`

```python
from django.db import models


class BillingCycle(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    ANNUAL = "annual", "Annual"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


# Lifecycle order for Goal 6's ?ordering=status. Explicit, because alphabetical
# order matching lifecycle order here is a coincidence, not a property.
STATUS_SORT_ORDER = {
    InvoiceStatus.DRAFT: 0,
    InvoiceStatus.ISSUED: 1,
    InvoiceStatus.PAID: 2,
    InvoiceStatus.VOID: 3,
}

# The only legal moves. Everything absent from this map is a 409.
ALLOWED_TRANSITIONS = {
    InvoiceStatus.DRAFT:  {InvoiceStatus.ISSUED, InvoiceStatus.VOID},
    InvoiceStatus.ISSUED: {InvoiceStatus.PAID, InvoiceStatus.VOID},
    InvoiceStatus.PAID:   set(),
    InvoiceStatus.VOID:   set(),
}


class EventType(models.TextChoices):
    CREATED = "created", "Created"
    STATUS_CHANGED = "status_changed", "Status changed"
    VOIDED = "voided", "Voided"
    FIELD_CHANGED = "field_changed", "Field changed"
    CREDIT_NOTE_ISSUED = "credit_note_issued", "Credit note issued"
    NOTE_ADDED = "note_added", "Note added"
```

---

## 2. `errors.py`

```python
"""Domain errors and the DRF exception handler.

Every failure the API can produce renders through one envelope:
    {"error": {"code": ..., "message": ..., "field": ..., "details": {...}}}
"""
import logging
import re

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db.utils import InternalError
from django.http import Http404
from rest_framework import status as http
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler
from rest_framework.exceptions import (
    APIException, ValidationError, PermissionDenied, NotAuthenticated,
)

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """A business rule refused the action. Carries a stable code and prose."""
    code = "DOMAIN_ERROR"
    http_status = http.HTTP_409_CONFLICT
    message = "This action is not allowed."

    def __init__(self, message=None, *, field=None, **details):
        self.message = message or self.message
        self.field = field
        self.details = details
        super().__init__(self.message)


# --- Invoice lifecycle (Goal 4) ---------------------------------------------
class InvalidTransition(DomainError):
    code = "INVALID_TRANSITION"

    def __init__(self, current, target):
        hint = ""
        if current == "draft" and target == "paid":
            hint = " An invoice must be issued before it can be marked paid."
        super().__init__(
            f"An invoice that is {current} cannot be {target}.{hint}",
            current_status=current, target_status=target,
        )


class InvoicePaidImmutable(DomainError):
    code = "INVOICE_PAID_IMMUTABLE"
    message = ("This invoice is paid and cannot be changed. "
               "Issue a credit note to correct it.")


class InvoicePaidCannotVoid(DomainError):
    code = "INVOICE_PAID_CANNOT_VOID"
    message = ("This invoice has been paid and cannot be voided. "
               "Issue a credit note against it instead.")


class InvoiceIssuedLocked(DomainError):
    code = "INVOICE_ISSUED_LOCKED"
    message = ("This invoice has been issued, so its billing period and amount "
               "are locked. You can still change its due date.")


class InvoiceVoidTerminal(DomainError):
    code = "INVOICE_VOID_IS_TERMINAL"
    message = "This invoice has been voided. Voided invoices cannot be changed."


class VoidReasonRequired(DomainError):
    code = "VOID_REASON_REQUIRED"
    http_status = http.HTTP_400_BAD_REQUEST
    message = "A reason is required when voiding an invoice."

    def __init__(self):
        super().__init__(field="reason")


class CreditNoteRequiresPaid(DomainError):
    code = "CREDIT_NOTE_REQUIRES_PAID"

    def __init__(self, current):
        super().__init__(
            f"Credit notes can only be issued against paid invoices. "
            f"This invoice is {current} — edit or void it instead.",
            current_status=current,
        )


class CreditExceedsInvoice(DomainError):
    code = "CREDIT_EXCEEDS_INVOICE"
    http_status = http.HTTP_400_BAD_REQUEST

    def __init__(self, amount, total, invoice_amount):
        super().__init__(
            f"A credit note of {amount} would bring total credits to {total}, "
            f"which is more than the invoice amount of {invoice_amount}.",
            field="amount",
            existing_total=str(total), invoice_amount=str(invoice_amount),
        )


# --- Subscriptions (Goals 2, 5) ---------------------------------------------
class PeriodAlreadyInvoiced(DomainError):
    code = "PERIOD_ALREADY_INVOICED"

    def __init__(self, start, end, invoice_id):
        super().__init__(
            f"An invoice already exists for {start} – {end}.",
            existing_invoice_id=str(invoice_id),
        )


class SubscriptionArchived(DomainError):
    code = "SUBSCRIPTION_ARCHIVED"
    message = ("This subscription is archived. Restore it before making "
               "changes or creating invoices.")


class AlreadyArchived(DomainError):
    code = "ALREADY_ARCHIVED"
    message = "This subscription is already archived."


class NotArchived(DomainError):
    code = "NOT_ARCHIVED"
    message = "This subscription is not archived."


class OwnerMustBeSelf(DomainError):
    code = "SUBSCRIPTION_OWNER_MUST_BE_SELF"
    http_status = http.HTTP_403_FORBIDDEN
    message = ("Account managers can only create subscriptions they own. "
               "Ask a billing admin to assign a different owner.")


class OwnerChangeAdminOnly(DomainError):
    code = "OWNER_CHANGE_ADMIN_ONLY"
    http_status = http.HTTP_403_FORBIDDEN
    message = "Only a billing admin can change a subscription's owner."


class CollaboratorMustBeAM(DomainError):
    code = "COLLABORATOR_MUST_BE_AM"
    http_status = http.HTTP_400_BAD_REQUEST
    message = "Only account managers can be added as collaborators."


class OwnerCannotBeCollaborator(DomainError):
    code = "OWNER_CANNOT_BE_COLLABORATOR"
    http_status = http.HTTP_400_BAD_REQUEST
    message = "This user already owns the subscription."


class AlreadyCollaborator(DomainError):
    code = "ALREADY_COLLABORATOR"
    message = "This user is already a collaborator on this subscription."


# --- Alerts (Goal 10) --------------------------------------------------------
class NotOverdue(DomainError):
    code = "NOT_OVERDUE"
    message = "This invoice is not overdue, so it has no alert to dismiss."


# --- Trigger backstop --------------------------------------------------------
# If one of these fires it means a service-layer check was missed. The user
# still gets a correct answer; the log line is how I find out.
TRIGGER_MAP = [
    (re.compile(r"is (paid|void) and immutable"), InvoicePaidImmutable),
    (re.compile(r"has a locked period and amount"), InvoiceIssuedLocked),
    (re.compile(r"append-only"),                    InvoicePaidImmutable),
    (re.compile(r"only a billing admin can archive"), OwnerChangeAdminOnly),
]


def _envelope(code, message, field=None, details=None, status_code=400):
    return Response(
        {"error": {"code": code, "message": message,
                   "field": field, "details": details or {}}},
        status=status_code,
    )


def exception_handler(exc, context):
    """Wired via REST_FRAMEWORK["EXCEPTION_HANDLER"]."""
    if isinstance(exc, DomainError):
        return _envelope(exc.code, exc.message, exc.field,
                         exc.details, exc.http_status)

    if isinstance(exc, InternalError):
        text = str(exc)
        for pattern, cls in TRIGGER_MAP:
            if pattern.search(text):
                logger.error("Database trigger fired — a service check was "
                             "missed: %s", text)
                err = cls()
                return _envelope(err.code, err.message, None, {},
                                 err.http_status)
        raise  # unknown InternalError — let it 500 loudly

    if isinstance(exc, Http404):
        return _envelope(
            "NOT_FOUND",
            "Not found, or not visible to you.",   # same text either way
            status_code=http.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        return _envelope("FORBIDDEN", str(getattr(exc, "detail", exc)),
                         status_code=http.HTTP_403_FORBIDDEN)

    if isinstance(exc, NotAuthenticated):
        return _envelope("UNAUTHENTICATED", str(exc.detail),
                         status_code=http.HTTP_401_UNAUTHORIZED)

    if isinstance(exc, ValidationError):
        detail = exc.detail
        field, message = None, "Some fields are invalid."
        if isinstance(detail, dict) and detail:
            field = next(iter(detail))
            first = detail[field]
            message = str(first[0] if isinstance(first, list) else first)
        elif isinstance(detail, list) and detail:
            message = str(detail[0])
        return _envelope("VALIDATION_ERROR", message, field,
                         {"fields": detail},
                         http.HTTP_400_BAD_REQUEST)

    response = drf_default_handler(exc, context)
    if response is not None:
        return _envelope(
            "ERROR",
            str(response.data.get("detail", response.data))
            if isinstance(response.data, dict) else str(response.data),
            status_code=response.status_code,
        )
    return None
```

---

## 3. `querysets.py`

```python
from datetime import timedelta

from django.db.models import (
    BooleanField, Case, DecimalField, F, IntegerField, Q, Sum, Value, When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from src.accounts.models import Role
from .enums import InvoiceStatus, STATUS_SORT_ORDER
from .models import Invoice, Subscription


def visible_subscriptions(user):
    qs = Subscription.objects.select_related("owner")
    if user.role == Role.BILLING_ADMIN:
        return qs
    return qs.filter(
        Q(owner_id=user.id) | Q(collaborators__user_id=user.id)
    ).distinct()          # the join duplicates rows — see test_subscriptions_api


def visible_invoices(user):
    qs = Invoice.objects.select_related("subscription", "subscription__owner")
    if user.role == Role.BILLING_ADMIN:
        return qs
    return qs.filter(
        Q(subscription__owner_id=user.id)
        | Q(subscription__collaborators__user_id=user.id)
    ).distinct()


def annotate_invoice_flags(qs, today=None):
    """is_overdue / days_overdue / credited_total, all computed in SQL.

    The client never derives these — see doc 07 §1 and risk R9.
    """
    today = today or timezone.localdate()
    overdue = Q(status=InvoiceStatus.ISSUED) & Q(due_date__lt=today)
    return qs.annotate(
        is_overdue=Case(When(overdue, then=Value(True)),
                        default=Value(False), output_field=BooleanField()),
        days_overdue=Case(
            When(overdue, then=Value(today) - F("due_date")),
            default=Value(timedelta(0)),
            output_field=IntegerField(),      # Postgres date subtraction → int
        ),
        credited_total=Coalesce(
            Sum("credit_notes__amount"),
            Value(0), output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        status_order=Case(
            *[When(status=s, then=Value(o)) for s, o in STATUS_SORT_ORDER.items()],
            output_field=IntegerField(),
        ),
    )


def active_alerts(user, today=None):
    """Goal 10 / ruling A-10 — the single definition.

    Both /api/alerts/ and /api/alerts/count/ call this, so the badge can never
    disagree with the list.
    """
    today = today or timezone.localdate()
    return (
        visible_invoices(user)
        .filter(status=InvoiceStatus.ISSUED, due_date__lt=today)
        .exclude(alert_dismissal__dismissed_for_due_date=F("due_date"))
    )
```

The `.exclude()` is the whole of A-10: a dismissal only suppresses the alert while it still points
at the invoice's *current* due date. Change the due date and the dismissal stops matching, so once
the new date passes the invoice alerts again.

---

## 4. `permissions.py`

```python
from rest_framework.permissions import BasePermission, SAFE_METHODS

from src.accounts.models import Role


class IsBillingAdmin(BasePermission):
    message = ("Only a billing admin can issue, mark paid, void or "
               "credit-note an invoice, archive a subscription, manage "
               "collaborators, or run bulk generation.")

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == Role.BILLING_ADMIN)


class IsSubscriptionMember(BasePermission):
    """Object-level: billing admin, owner, or collaborator.

    Rarely reached — the querysets already 404 a stranger. It exists so a view
    that forgets to scope its queryset still fails closed.
    """
    message = "You do not own or collaborate on this subscription."

    def has_object_permission(self, request, view, obj):
        u = request.user
        if u.role == Role.BILLING_ADMIN:
            return True
        sub = obj if hasattr(obj, "owner_id") else obj.subscription
        return (sub.owner_id == u.id
                or sub.collaborators.filter(user_id=u.id).exists())


class ReadOnlyOrBillingAdmin(BasePermission):
    message = "Only a billing admin can change this."

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return request.method in SAFE_METHODS or u.role == Role.BILLING_ADMIN
```

`src/accounts/permissions.py` is superseded by this file for billing views. Delete
`IsOwnerOrCollaboratorOrAdmin` and `CanManageInvoiceLifecycle` from it (defect D-09) rather than
leaving two versions of the same rule in the tree.

---

## 5. `pagination.py`

```python
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Goal 6 requires the total number of matches, which `count` provides."""
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
```

---

## 6. `filters.py`

```python
import django_filters as df
from django.db.models import Q
from django.utils import timezone

from .enums import InvoiceStatus
from .models import Invoice, Subscription


class InvoiceFilterSet(df.FilterSet):
    """Goal 6. Every filter resolves to SQL — nothing reaches the browser
    unfiltered."""

    search = df.CharFilter(method="filter_search")
    status = df.MultipleChoiceFilter(choices=InvoiceStatus.choices)
    overdue = df.BooleanFilter(method="filter_overdue")
    owner = df.UUIDFilter(field_name="subscription__owner_id")
    subscription = df.UUIDFilter(field_name="subscription_id")
    due_before = df.DateFilter(field_name="due_date", lookup_expr="lte")
    due_after = df.DateFilter(field_name="due_date", lookup_expr="gte")

    class Meta:
        model = Invoice
        fields = []

    def filter_search(self, qs, name, value):
        value = value.strip()
        if not value:
            return qs
        return qs.filter(
            Q(subscription__customer_name__icontains=value)
            | Q(subscription__billing_email__icontains=value)
        )

    def filter_overdue(self, qs, name, value):
        today = timezone.localdate()
        cond = Q(status=InvoiceStatus.ISSUED, due_date__lt=today)
        return qs.filter(cond) if value else qs.exclude(cond)


# ?ordering=<key> → ORM ordering. status maps to the annotated lifecycle
# order, not the alphabet.
INVOICE_ORDERING = {
    "due_date": ["due_date"],   "-due_date": ["-due_date"],
    "amount":   ["amount"],     "-amount":   ["-amount"],
    "status":   ["status_order"], "-status": ["-status_order"],
    "created_at": ["created_at"], "-created_at": ["-created_at"],
}
DEFAULT_INVOICE_ORDERING = ["-due_date"]


class SubscriptionFilterSet(df.FilterSet):
    search = df.CharFilter(method="filter_search")
    archived = df.CharFilter(method="filter_archived")   # true | false | all
    owner = df.UUIDFilter(field_name="owner_id")
    plan = df.CharFilter(field_name="plan_name", lookup_expr="iexact")

    class Meta:
        model = Subscription
        fields = []

    def filter_search(self, qs, name, value):
        value = value.strip()
        if not value:
            return qs
        return qs.filter(Q(customer_name__icontains=value)
                         | Q(billing_email__icontains=value))

    def filter_archived(self, qs, name, value):
        v = (value or "false").lower()
        if v == "all":
            return qs
        return qs.filter(archived_at__isnull=(v != "true"))
```

`archived` defaults to `false` — an unfiltered subscription list shows active work. The default is
applied in the view, not here, because a FilterSet only sees params that were sent.

---

## 7. `serializers.py`

```python
from decimal import Decimal

from rest_framework import serializers

from src.accounts.models import Role, User
from .enums import BillingCycle, InvoiceStatus
from .models import (
    AlertDismissal, Collaborator, CreditNote, Invoice, InvoiceEvent, Subscription,
)

# DRF's COERCE_DECIMAL_TO_STRING default is True and stays on — money crosses
# the wire as a string, never as a float. See doc 05 §1.
MONEY = dict(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "role"]


# --- Subscriptions -----------------------------------------------------------
class SubscriptionSerializer(serializers.ModelSerializer):
    owner = UserBriefSerializer(read_only=True)
    owner_id = serializers.UUIDField(write_only=True, required=False)
    collaborators = serializers.SerializerMethodField()
    is_archived = serializers.SerializerMethodField()
    invoice_summary = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id", "customer_name", "billing_email", "plan_name",
            "billing_cycle", "price", "start_date",
            "owner", "owner_id", "collaborators",
            "archived_at", "is_archived", "invoice_summary",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "archived_at", "created_at", "updated_at"]
        extra_kwargs = {"price": MONEY}

    def get_is_archived(self, obj):
        return obj.archived_at is not None

    def get_collaborators(self, obj):
        # prefetch_related("collaborators__user") in the view — no N+1
        return [UserBriefSerializer(c.user).data for c in obj.collaborators.all()]

    def get_invoice_summary(self, obj):
        # populated by the view's annotations; None on the detail endpoint
        if not hasattr(obj, "inv_total"):
            return None
        return {
            "total": obj.inv_total,
            "draft": obj.inv_draft, "issued": obj.inv_issued,
            "paid": obj.inv_paid,   "void": obj.inv_void,
            "outstanding": str(obj.inv_outstanding or Decimal("0.00")),
        }

    def validate_billing_email(self, v):
        return v.strip().lower()

    def validate_plan_name(self, v):
        return v.strip()          # keeps "Pro" and "Pro " from splitting (doc 03 §7)


class SubscriptionDetailSerializer(SubscriptionSerializer):
    invoices = serializers.SerializerMethodField()

    class Meta(SubscriptionSerializer.Meta):
        fields = SubscriptionSerializer.Meta.fields + ["invoices"]

    def get_invoices(self, obj):
        # Goal 3: "Opening a subscription shows all of its invoices."
        qs = obj.invoices.all().order_by("-period_start")
        return InvoiceListSerializer(qs, many=True, context=self.context).data


class CollaboratorCreateSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


# --- Invoices ----------------------------------------------------------------
class InvoiceListSerializer(serializers.ModelSerializer):
    """Flattened for the Goal 6 table — no nested fetch per row."""
    customer_name = serializers.CharField(source="subscription.customer_name",
                                          read_only=True)
    billing_email = serializers.CharField(source="subscription.billing_email",
                                          read_only=True)
    plan_name = serializers.CharField(source="subscription.plan_name",
                                      read_only=True)
    owner_email = serializers.CharField(source="subscription.owner.email",
                                        read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)      # annotated
    days_overdue = serializers.IntegerField(read_only=True)    # annotated
    credited_total = serializers.DecimalField(read_only=True, **MONEY)

    class Meta:
        model = Invoice
        fields = [
            "id", "subscription_id", "customer_name", "billing_email",
            "plan_name", "owner_email", "period_start", "period_end",
            "amount", "due_date", "status", "void_reason",
            "is_overdue", "days_overdue", "credited_total",
            "issued_at", "paid_at", "created_at",
        ]


class InvoiceCreateSerializer(serializers.Serializer):
    subscription_id = serializers.UUIDField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    amount = serializers.DecimalField(**MONEY)
    due_date = serializers.DateField()
    # `status` is deliberately absent — nobody creates a non-draft invoice.

    def validate(self, data):
        if data["period_start"] > data["period_end"]:
            raise serializers.ValidationError(
                {"period_end": "The period end must be on or after the start."})
        return data


class InvoiceUpdateSerializer(serializers.Serializer):
    """Which of these are accepted depends on status — enforced in the
    service, not here, so one rule lives in one place (doc 05 §4)."""
    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    amount = serializers.DecimalField(required=False, **MONEY)
    due_date = serializers.DateField(required=False)


class CreditNoteSerializer(serializers.ModelSerializer):
    created_by = UserBriefSerializer(read_only=True)

    class Meta:
        model = CreditNote
        fields = ["id", "invoice_id", "amount", "reason",
                  "created_by", "created_at"]
        read_only_fields = ["id", "invoice_id", "created_by", "created_at"]
        extra_kwargs = {"amount": MONEY}

    def validate_reason(self, v):
        if not v.strip():
            raise serializers.ValidationError("A reason is required.")
        return v.strip()


class InvoiceEventSerializer(serializers.ModelSerializer):
    actor = UserBriefSerializer(read_only=True)

    class Meta:
        model = InvoiceEvent
        fields = ["id", "event_type", "old_status", "new_status",
                  "actor", "details", "created_at"]
        read_only_fields = fields      # Goal 9 — nothing here is writable


class InvoiceDetailSerializer(InvoiceListSerializer):
    subscription = SubscriptionSerializer(read_only=True)
    credit_notes = CreditNoteSerializer(many=True, read_only=True)
    timeline = serializers.SerializerMethodField()
    net_amount = serializers.SerializerMethodField()

    class Meta(InvoiceListSerializer.Meta):
        fields = InvoiceListSerializer.Meta.fields + [
            "subscription", "credit_notes", "timeline", "net_amount",
        ]

    def get_timeline(self, obj):
        qs = obj.events.select_related("actor").order_by("created_at")
        return InvoiceEventSerializer(qs, many=True).data

    def get_net_amount(self, obj):
        return str(obj.amount - (obj.credited_total or Decimal("0.00")))


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class NoteSerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=False, trim_whitespace=True,
                                 max_length=2000)


class BulkGenerateSerializer(serializers.Serializer):
    as_of = serializers.DateField(required=False)
```

---

## 8. `services/bulk.py` (Goal 7)

```python
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..enums import EventType
from ..errors import DomainError
from ..models import Invoice, Subscription
from ..periods import NET_DAYS, current_period
from . import invoices as invoice_service


def bulk_generate(user, as_of=None):
    """Generate the current period's invoice for every active subscription.

    Returns Goal 7's per-subscription report: generated / skipped / failed,
    every non-generated row carrying a reason a human can act on.
    """
    as_of = as_of or timezone.localdate()
    subs = (Subscription.objects
            .filter(archived_at__isnull=True)        # I-14 / Goal 2
            .select_related("owner")
            .order_by("customer_name"))

    results = []
    for sub in subs:
        results.append(_generate_one(sub, as_of, user))

    summary = {"total": len(results)}
    for outcome in ("generated", "skipped", "failed"):
        summary[outcome] = sum(1 for r in results if r["outcome"] == outcome)
    return {"as_of": as_of, "summary": summary, "results": results}


def _generate_one(sub, as_of, user):
    row = {"subscription_id": str(sub.id), "customer_name": sub.customer_name}

    period = current_period(sub.start_date, sub.billing_cycle, as_of)
    if period is None:                                        # ruling A-13
        return {**row, "outcome": "skipped",
                "reason": f"Subscription has not started "
                          f"(starts {sub.start_date})"}

    start, end = period
    existing = (Invoice.objects
                .filter(subscription=sub, period_start=start, period_end=end)
                .exclude(status="void")                       # ruling A-14
                .first())
    if existing:
        return {**row, "outcome": "skipped",
                "reason": f"An invoice already exists for {start} – {end}",
                "invoice_id": str(existing.id)}

    try:
        # Savepoint per subscription: one bad row must not roll back the run.
        with transaction.atomic():
            inv = invoice_service.create_invoice(
                subscription=sub, period_start=start, period_end=end,
                amount=sub.price, due_date=start + NET_DAYS,
                actor=user, source="bulk",
            )
    except IntegrityError:
        # Lost a race against a concurrent run. Landing on the right end state
        # is not an error — report it the same way as any other duplicate.
        return {**row, "outcome": "skipped",
                "reason": f"An invoice already exists for {start} – {end}"}
    except DomainError as exc:
        return {**row, "outcome": "failed", "reason": exc.message}
    except Exception as exc:                                   # noqa: BLE001
        return {**row, "outcome": "failed", "reason": str(exc)}

    return {**row, "outcome": "generated", "invoice_id": str(inv.id),
            "period_start": start, "period_end": end, "amount": str(inv.amount)}
```

---

## 9. `services/dashboard.py` (Goal 8)

```python
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncWeek
from django.utils import timezone

from ..enums import InvoiceStatus
from ..models import CreditNote
from ..querysets import visible_invoices

ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14,
                                                        decimal_places=2))


def build(user, today=None):
    today = today or timezone.localdate()
    month_start = today.replace(day=1)
    invoices = visible_invoices(user)

    return {
        "as_of": today,
        "headline": _headline(user, invoices, today, month_start),
        "by_status": _by_status(invoices),
        "by_plan": _by_plan(invoices),
        "revenue_by_week": _revenue_by_week(invoices, today),
    }


def _headline(user, invoices, today, month_start):
    # A-08: "issued this month" reads issued_at, not current status. An invoice
    # issued in March and paid in April still counts as issued in March.
    issued = invoices.filter(issued_at__date__gte=month_start).count()

    # A-09: collected reads paid_at.
    collected = invoices.filter(paid_at__date__gte=month_start).aggregate(
        t=Coalesce(Sum("amount"), ZERO))["t"]

    # A-06: credits are reported beside revenue, never netted into it.
    credits = (CreditNote.objects
               .filter(invoice__in=invoices, created_at__date__gte=month_start)
               .aggregate(t=Coalesce(Sum("amount"), ZERO))["t"])

    receivables = invoices.filter(status=InvoiceStatus.ISSUED).aggregate(
        t=Coalesce(Sum("amount"), ZERO))["t"]

    overdue = invoices.filter(status=InvoiceStatus.ISSUED, due_date__lt=today)
    overdue_agg = overdue.aggregate(n=Count("id"),
                                    t=Coalesce(Sum("amount"), ZERO))

    return {
        "invoices_issued_this_month": issued,
        "revenue_collected_this_month": str(collected),
        "credits_issued_this_month": str(credits),
        "receivables": str(receivables),
        "invoices_overdue": overdue_agg["n"],
        "overdue_amount": str(overdue_agg["t"]),
    }


def _by_status(invoices):
    rows = {r["status"]: r for r in invoices.values("status").annotate(
        count=Count("id"), amount=Coalesce(Sum("amount"), ZERO))}
    # Emit every status, including the empty ones — a breakdown that hides
    # zeros makes the reader guess whether the category exists.
    return [{"status": s.value,
             "count": rows.get(s.value, {}).get("count", 0),
             "amount": str(rows.get(s.value, {}).get("amount", Decimal("0.00")))}
            for s in InvoiceStatus]


def _by_plan(invoices):
    rows = (invoices.values("subscription__plan_name")
            .annotate(count=Count("id"), amount=Coalesce(Sum("amount"), ZERO))
            .order_by("-amount"))
    return [{"plan_name": r["subscription__plan_name"],
             "count": r["count"], "amount": str(r["amount"])} for r in rows]


def _revenue_by_week(invoices, today):
    """Exactly 8 buckets, oldest first, zeros included.

    The backend emits the empty weeks so the chart cannot silently rescale its
    own x-axis and mislead.
    """
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=7)

    rows = (invoices
            .filter(paid_at__date__gte=first)
            .annotate(week=TruncWeek("paid_at"))
            .values("week")
            .annotate(amount=Coalesce(Sum("amount"), ZERO)))
    found = {r["week"].date(): r["amount"] for r in rows if r["week"]}

    return [{"week_start": (w := first + timedelta(weeks=i)),
             "amount": str(found.get(w, Decimal("0.00")))} for i in range(8)]
```

---

## 10. `services/alerts.py` (Goal 10)

```python
from django.db import transaction
from django.utils import timezone

from src.accounts.models import Role
from ..enums import InvoiceStatus
from ..errors import NotOverdue
from ..models import AlertDismissal
from ..querysets import active_alerts, visible_invoices


def list_alerts(user, today=None):
    today = today or timezone.localdate()
    qs = (active_alerts(user, today)
          .select_related("subscription", "subscription__owner")
          .order_by("due_date"))
    dismissible = user.role == Role.BILLING_ADMIN        # ruling A-11
    return [{
        "invoice_id": str(i.id),
        "subscription_id": str(i.subscription_id),
        "customer_name": i.subscription.customer_name,
        "amount": str(i.amount),
        "due_date": i.due_date,
        "days_overdue": (today - i.due_date).days,
        "dismissible": dismissible,
    } for i in qs]


def count_alerts(user, today=None):
    # Same queryset as list_alerts — the badge cannot disagree with the list.
    return active_alerts(user, today).count()


@transaction.atomic
def dismiss(invoice_id, user, today=None):
    today = today or timezone.localdate()
    invoice = visible_invoices(user).select_for_update().get(pk=invoice_id)
    if not (invoice.status == InvoiceStatus.ISSUED and invoice.due_date < today):
        raise NotOverdue()

    # Upsert: record the due date this dismissal was made against. That value
    # is the entire A-10 re-arming mechanism.
    AlertDismissal.objects.update_or_create(
        invoice=invoice,
        defaults={"dismissed_for_due_date": invoice.due_date,
                  "dismissed_by": user,
                  "dismissed_at": timezone.now()},
    )
    # Deliberately no invoice_event — dismissal is about the operator's
    # attention, not a fact about the invoice (doc 05 §6).
    return invoice
```

---

## 11. `views/` — the router decision

**ViewSets with `@action` methods**, routed by `DefaultRouter`. Chosen over bare `APIView`s because
the transition endpoints are naturally sub-resources of an invoice and `@action` gives them URLs and
permissions without a hand-written `urls.py` of twenty lines.

```python
# views/invoices.py
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..enums import InvoiceStatus
from ..filters import DEFAULT_INVOICE_ORDERING, INVOICE_ORDERING, InvoiceFilterSet
from ..pagination import DefaultPagination
from ..permissions import IsBillingAdmin, IsSubscriptionMember
from ..querysets import annotate_invoice_flags, visible_invoices
from ..serializers import (
    CreditNoteSerializer, InvoiceCreateSerializer, InvoiceDetailSerializer,
    InvoiceEventSerializer, InvoiceListSerializer, InvoiceUpdateSerializer,
    NoteSerializer, VoidSerializer,
)
from ..services import alerts as alert_service
from ..services import invoices as service


class InvoiceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsSubscriptionMember]
    pagination_class = DefaultPagination
    filterset_class = InvoiceFilterSet

    def get_queryset(self):
        qs = annotate_invoice_flags(visible_invoices(self.request.user))
        if self.action == "retrieve":
            return qs.prefetch_related("credit_notes", "events__actor")
        return qs

    def filter_queryset(self, qs):
        qs = super().filter_queryset(qs)
        key = self.request.query_params.get("ordering")
        return qs.order_by(*INVOICE_ORDERING.get(key, DEFAULT_INVOICE_ORDERING))

    def get_serializer_class(self):
        return (InvoiceDetailSerializer if self.action == "retrieve"
                else InvoiceListSerializer)

    # --- writes -------------------------------------------------------------
    def create(self, request):
        s = InvoiceCreateSerializer(data=request.data); s.is_valid(raise_exception=True)
        inv = service.create_invoice(actor=request.user, **s.validated_data)
        return Response(self._detail(inv), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        inv = self.get_object()
        s = InvoiceUpdateSerializer(data=request.data); s.is_valid(raise_exception=True)
        inv = service.edit_invoice(inv, actor=request.user, **s.validated_data)
        return Response(self._detail(inv))

    # --- lifecycle, billing admin only (Goal 1 + Goal 4) --------------------
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsBillingAdmin])
    def issue(self, request, pk=None):
        inv = service.transition(self.get_object(), InvoiceStatus.ISSUED, request.user)
        return Response(self._detail(inv))

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsBillingAdmin])
    def pay(self, request, pk=None):
        inv = service.transition(self.get_object(), InvoiceStatus.PAID, request.user)
        return Response(self._detail(inv))

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsBillingAdmin])
    def void(self, request, pk=None):
        s = VoidSerializer(data=request.data); s.is_valid(raise_exception=True)
        inv = service.transition(self.get_object(), InvoiceStatus.VOID,
                                 request.user, reason=s.validated_data["reason"])
        return Response(self._detail(inv))

    @action(detail=True, methods=["post"], url_path="credit-notes",
            permission_classes=[IsAuthenticated, IsBillingAdmin])
    def credit_notes(self, request, pk=None):
        s = CreditNoteSerializer(data=request.data); s.is_valid(raise_exception=True)
        cn = service.add_credit_note(self.get_object(), actor=request.user,
                                     **s.validated_data)
        return Response(CreditNoteSerializer(cn).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="dismiss-alert",
            permission_classes=[IsAuthenticated, IsBillingAdmin])
    def dismiss_alert(self, request, pk=None):
        inv = alert_service.dismiss(pk, request.user)
        return Response({"dismissed_for_due_date": inv.due_date})

    # --- notes and timeline (Goal 9) ----------------------------------------
    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        s = NoteSerializer(data=request.data); s.is_valid(raise_exception=True)
        ev = service.add_note(self.get_object(), request.user, s.validated_data["text"])
        return Response(InvoiceEventSerializer(ev).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        qs = self.get_object().events.select_related("actor").order_by("created_at")
        return Response(InvoiceEventSerializer(qs, many=True).data)

    def _detail(self, inv):
        inv = annotate_invoice_flags(
            visible_invoices(self.request.user)).get(pk=inv.pk)
        return InvoiceDetailSerializer(inv, context=self.get_serializer_context()).data
```

**No `destroy`, no `update` (PUT).** Only `partial_update`. There is no endpoint that deletes an
invoice, and a PUT would invite a client to send a whole object including `status`.

`SubscriptionViewSet` follows the same shape with `@action`s for `archive`, `restore`,
`collaborators` (POST) and `collaborators/<user_id>` (DELETE), all `IsBillingAdmin`.

---

## 12. `urls.py`

```python
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views.alerts import AlertListView, AlertCountView
from .views.dashboard import DashboardView
from .views.exports import ReceivablesCSVView
from .views.invoices import BulkGenerateView, InvoiceViewSet
from .views.subscriptions import SubscriptionViewSet

router = DefaultRouter()
router.register("subscriptions", SubscriptionViewSet, basename="subscription")
router.register("invoices", InvoiceViewSet, basename="invoice")

urlpatterns = [
    path("invoices/bulk-generate/", BulkGenerateView.as_view()),  # before router
    path("dashboard/", DashboardView.as_view()),
    path("alerts/", AlertListView.as_view()),
    path("alerts/count/", AlertCountView.as_view()),
    path("exports/receivables.csv", ReceivablesCSVView.as_view()),
    path("", include(router.urls)),
]
```

`bulk-generate/` is declared **before** `include(router.urls)`. The router's detail route matches
`invoices/<pk>/`, and without the earlier declaration Django would try to resolve `bulk-generate`
as a UUID primary key and 404.

---

## 13. `views/exports.py` (Goal 7)

```python
import csv
from datetime import date

from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from ..enums import InvoiceStatus
from ..filters import InvoiceFilterSet
from ..querysets import annotate_invoice_flags, visible_invoices

HEADERS = ["invoice_id", "customer_name", "billing_email", "plan_name",
           "owner_email", "period_start", "period_end", "amount",
           "due_date", "days_overdue", "status"]


class _Echo:
    """csv.writer needs a file-like object; this one just returns the line."""
    def write(self, value):
        return value


class ReceivablesCSVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = annotate_invoice_flags(visible_invoices(request.user)).filter(
            status=InvoiceStatus.ISSUED)               # receivables = issued
        qs = InvoiceFilterSet(request.query_params, queryset=qs).qs
        qs = qs.select_related("subscription", "subscription__owner") \
               .order_by("due_date")

        writer = csv.writer(_Echo())

        def rows():
            yield writer.writerow(HEADERS)
            for i in qs.iterator(chunk_size=500):
                yield writer.writerow([
                    i.id, i.subscription.customer_name,
                    i.subscription.billing_email, i.subscription.plan_name,
                    i.subscription.owner.email, i.period_start, i.period_end,
                    str(i.amount),                     # str(Decimal), never %f
                    i.due_date, i.days_overdue, i.status,
                ])

        filename = f"receivables-{date.today()}.csv"
        response = StreamingHttpResponse(rows(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
```

`csv.writer` handles quoting, so a customer named `Acme, Inc.` is escaped correctly — the test for
that is in `test_export.py`.

---

## 14. `settings.py` diff

```python
INSTALLED_APPS = [
    # ... existing entries unchanged ...
    "django_filters",        # NEW
    "src.accounts",
    "src.billing",           # NEW
]

REST_FRAMEWORK = {
    # ... existing keys unchanged ...
    "DEFAULT_FILTER_BACKENDS": (                                     # NEW
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    "DEFAULT_PAGINATION_CLASS": "src.billing.pagination.DefaultPagination",  # NEW
    "PAGE_SIZE": 25,                                                 # NEW
    "EXCEPTION_HANDLER": "src.billing.errors.exception_handler",     # CHANGED
}

if not DEBUG:                                                        # NEW block
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {                                                          # NEW
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        # Trigger firings are logged here — each one is a service-layer bug.
        "src.billing": {"handlers": ["console"], "level": "INFO"},
    },
}
```

`SECURE_PROXY_SSL_HEADER` is the line that causes an infinite redirect loop on Render if omitted
alongside `SECURE_SSL_REDIRECT`. Both go in together or neither does.
