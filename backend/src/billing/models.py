import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from .enums import BillingCycle, EventType, InvoiceStatus


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_name = models.CharField(max_length=255)
    billing_email = models.EmailField(max_length=255)
    plan_name = models.CharField(max_length=100)
    billing_cycle = models.CharField(max_length=10, choices=BillingCycle.choices)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_subscriptions",
    )
    # Non-null means archived. Archiving stops generation without destroying
    # invoice history (Goal 2).
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscriptions"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gt=0), name="sub_price_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["owner"], name="idx_sub_owner"),
            models.Index(fields=["plan_name"], name="idx_sub_plan"),
            models.Index(
                fields=["archived_at"],
                name="idx_sub_active",
                condition=Q(archived_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.customer_name} ({self.plan_name})"

    @property
    def is_archived(self):
        return self.archived_at is not None


class Collaborator(models.Model):
    """Additional account managers with edit and invoice-create rights.

    Pure access-grant metadata with no historical value, so both foreign keys
    CASCADE. Contrast Subscription.owner, which is PROTECTed because it is part
    of the subscription's identity.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="collaborators"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="collaborations",
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collaborators_added",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "collaborators"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "user"], name="uq_collaborator"
            ),
        ]
        indexes = [
            # Serves the RLS EXISTS check: given a subscription, is this user on it.
            models.Index(
                fields=["subscription", "user"], name="idx_collab_sub_user"
            ),
            # Serves "my subscriptions": given a user, which subscriptions.
            # The composite above cannot serve this — wrong leading column.
            models.Index(fields=["user"], name="idx_collab_user"),
        ]

    def __str__(self):
        return f"{self.user_id} on {self.subscription_id}"


class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name="invoices"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT
    )
    void_reason = models.TextField(null=True, blank=True)
    # Denormalised from the event trail so the dashboard's monthly figures are
    # indexed range scans rather than joins against invoice_events. The trail
    # remains the source of truth; services.invoices.transition is the only
    # writer of both, in one transaction.
    issued_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-period_start"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="inv_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(period_start__lte=models.F("period_end")),
                name="inv_period_ordered",
            ),
            # status = void  <=>  a reason exists
            models.CheckConstraint(
                condition=(
                    Q(status=InvoiceStatus.VOID, void_reason__isnull=False)
                    | (~Q(status=InvoiceStatus.VOID) & Q(void_reason__isnull=True))
                ),
                name="inv_void_has_reason",
            ),
            # Partial: voiding must free the period so a corrected invoice can
            # be generated for it (ruling A-14).
            models.UniqueConstraint(
                fields=["subscription", "period_start", "period_end"],
                condition=~Q(status=InvoiceStatus.VOID),
                name="uq_invoice_period",
            ),
        ]
        indexes = [
            models.Index(fields=["subscription"], name="idx_inv_sub"),
            models.Index(fields=["status", "due_date"], name="idx_inv_status_due"),
            models.Index(fields=["due_date"], name="idx_inv_due"),
            models.Index(
                fields=["paid_at"],
                name="idx_inv_paid_at",
                condition=Q(paid_at__isnull=False),
            ),
            models.Index(
                fields=["issued_at"],
                name="idx_inv_issued_at",
                condition=Q(issued_at__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.subscription_id} {self.period_start}..{self.period_end}"

    @property
    def is_overdue(self):
        """Ruling A-07. Mirrors the SQL annotation in querysets.py exactly —
        two definitions drifting apart would put a wrong badge next to a
        correct filter."""
        if hasattr(self, "_is_overdue"):
            return self._is_overdue
        return (
            self.status == InvoiceStatus.ISSUED
            and self.due_date < timezone.localdate()
        )

    @is_overdue.setter
    def is_overdue(self, value):
        self._is_overdue = value

    @property
    def days_overdue(self):
        if hasattr(self, "_days_overdue"):
            val = self._days_overdue
            if hasattr(val, "days"):
                return val.days
            return val or 0
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_date).days

    @days_overdue.setter
    def days_overdue(self, value):
        self._days_overdue = value

    @property
    def credited_total(self):
        """Prefer the annotated value in list contexts — this is a query."""
        if hasattr(self, "_credited_total"):
            return self._credited_total
        total = self.credit_notes.aggregate(t=Sum("amount"))["t"]
        return total or Decimal("0.00")

    @credited_total.setter
    def credited_total(self, value):
        self._credited_total = value


class CreditNote(models.Model):
    """An immutable correction against a Paid invoice.

    Stands as its own record rather than altering the original (Goal 4).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="credit_notes"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_notes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "credit_notes"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="cn_amount_positive"
            ),
        ]
        indexes = [models.Index(fields=["invoice"], name="idx_cn_invoice")]


class InvoiceEvent(models.Model):
    """One row in an invoice's timeline. Append-only (Goal 9).

    Enforced by trigger, by the absence of an RLS UPDATE/DELETE policy, and by
    there being no route that mutates one.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    # First-class columns rather than JSONB keys: Goal 9 names them
    # specifically, and the dashboard queries them.
    old_status = models.CharField(max_length=10, null=True, blank=True)
    new_status = models.CharField(max_length=10, null=True, blank=True)
    # SET_NULL, not PROTECT: the event must outlive the actor. The timeline
    # renders "(deleted user)" rather than pinning a user forever.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_events",
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoice_events"
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["invoice", "created_at"], name="idx_evt_invoice_time"
            ),
            models.Index(
                fields=["new_status", "created_at"],
                name="idx_evt_status_time",
                condition=Q(event_type=EventType.STATUS_CHANGED),
            ),
        ]


class AlertDismissal(models.Model):
    """A billing admin's dismissal of an overdue-invoice alert (Goal 10).

    Its own table, not a column on Invoice, because recording a dismissal must
    not UPDATE an invoice that may be immutable. A column would force a hole in
    the immutability trigger, and every hole in an immutability rule is a place
    the rule later leaks.

    dismissed_for_due_date is the whole re-arming mechanism (ruling A-10): the
    dismissal only suppresses the alert while it still points at the invoice's
    current due date.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.OneToOneField(
        Invoice, on_delete=models.CASCADE, related_name="alert_dismissal"
    )
    dismissed_for_due_date = models.DateField()
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts_dismissed",
    )
    dismissed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "alert_dismissals"
