"""Serializers.

DRF's COERCE_DECIMAL_TO_STRING default is True and stays on: money crosses the
wire as a string, never as a JSON number. A JSON number becomes an IEEE double
in every JS client, and that is not a property you want in a billing system.
"""

from decimal import Decimal

from rest_framework import serializers

from src.accounts.models import User

from .models import CreditNote, Invoice, InvoiceEvent, Subscription

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
        # The view prefetches collaborators__user — no N+1 here.
        return [UserBriefSerializer(c.user).data for c in obj.collaborators.all()]

    def get_invoice_summary(self, obj):
        # Populated by the list view's annotations; absent on detail.
        if not hasattr(obj, "inv_total"):
            return None
        return {
            "total": obj.inv_total,
            "draft": obj.inv_draft,
            "issued": obj.inv_issued,
            "paid": obj.inv_paid,
            "void": obj.inv_void,
            "outstanding": str(obj.inv_outstanding or Decimal("0.00")),
        }

    def validate_billing_email(self, value):
        return value.strip().lower()

    def validate_plan_name(self, value):
        # Trim on write so "Pro" and "Pro " do not split the by-plan breakdown.
        return value.strip()

    def validate_customer_name(self, value):
        return value.strip()


class SubscriptionDetailSerializer(SubscriptionSerializer):
    invoices = serializers.SerializerMethodField()

    class Meta(SubscriptionSerializer.Meta):
        fields = SubscriptionSerializer.Meta.fields + ["invoices"]

    def get_invoices(self, obj):
        # Goal 3: "Opening a subscription shows all of its invoices."
        from .querysets import annotate_invoice_flags

        qs = annotate_invoice_flags(obj.invoices.all()).order_by("-period_start")
        return InvoiceListSerializer(qs, many=True, context=self.context).data


class SubscriptionCreateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255)
    billing_email = serializers.EmailField(max_length=255)
    plan_name = serializers.CharField(max_length=100)
    billing_cycle = serializers.ChoiceField(choices=["monthly", "annual"])
    price = serializers.DecimalField(**MONEY)
    start_date = serializers.DateField()
    owner_id = serializers.UUIDField(required=False, allow_null=True)


class SubscriptionUpdateSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255, required=False)
    billing_email = serializers.EmailField(max_length=255, required=False)
    plan_name = serializers.CharField(max_length=100, required=False)
    billing_cycle = serializers.ChoiceField(
        choices=["monthly", "annual"], required=False
    )
    price = serializers.DecimalField(required=False, **MONEY)
    start_date = serializers.DateField(required=False)
    owner_id = serializers.UUIDField(required=False, allow_null=True)


class CollaboratorCreateSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


# --- Invoices ----------------------------------------------------------------


class InvoiceListSerializer(serializers.ModelSerializer):
    """Flattened for the Goal 6 table — no nested fetch per row."""

    customer_name = serializers.CharField(
        source="subscription.customer_name", read_only=True
    )
    billing_email = serializers.CharField(
        source="subscription.billing_email", read_only=True
    )
    plan_name = serializers.CharField(
        source="subscription.plan_name", read_only=True
    )
    owner_email = serializers.CharField(
        source="subscription.owner.email", read_only=True
    )
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)
    credited_total = serializers.DecimalField(
        read_only=True, max_digits=12, decimal_places=2
    )

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
    # `status` is deliberately absent: nobody creates a non-draft invoice.

    def validate(self, data):
        if data["period_start"] > data["period_end"]:
            raise serializers.ValidationError(
                {"period_end": "The period end must be on or after the start."}
            )
        return data


class InvoiceUpdateSerializer(serializers.Serializer):
    """Which of these are accepted depends on the invoice's status. That is
    enforced in the service, not here, so the rule lives in one place."""

    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)
    amount = serializers.DecimalField(required=False, **MONEY)
    due_date = serializers.DateField(required=False)


class CreditNoteSerializer(serializers.ModelSerializer):
    created_by = UserBriefSerializer(read_only=True)

    class Meta:
        model = CreditNote
        fields = ["id", "invoice_id", "amount", "reason", "created_by", "created_at"]
        read_only_fields = ["id", "invoice_id", "created_by", "created_at"]
        extra_kwargs = {"amount": MONEY}

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("A reason is required.")
        return value.strip()


class InvoiceEventSerializer(serializers.ModelSerializer):
    actor = UserBriefSerializer(read_only=True)

    class Meta:
        model = InvoiceEvent
        # Goal 9: nothing here is writable, and no route exists that would
        # accept a write anyway.
        fields = [
            "id", "event_type", "old_status", "new_status",
            "actor", "details", "created_at",
        ]
        read_only_fields = fields


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
        credited = getattr(obj, "credited_total", None)
        if credited is None:
            credited = obj.credited_total
        return str(obj.amount - (credited or Decimal("0.00")))


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)


class NoteSerializer(serializers.Serializer):
    text = serializers.CharField(
        allow_blank=False, trim_whitespace=True, max_length=2000
    )


class BulkGenerateSerializer(serializers.Serializer):
    as_of = serializers.DateField(required=False)
