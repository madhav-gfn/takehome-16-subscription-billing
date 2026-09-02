from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..enums import InvoiceStatus
from ..filters import (
    DEFAULT_INVOICE_ORDERING,
    INVOICE_ORDERING,
    InvoiceFilterSet,
)
from ..pagination import DefaultPagination
from ..permissions import IsBillingAdmin, IsSubscriptionMember
from ..querysets import (
    annotate_invoice_flags,
    visible_invoices,
    visible_subscriptions,
)
from ..serializers import (
    BulkGenerateSerializer,
    CreditNoteSerializer,
    InvoiceCreateSerializer,
    InvoiceDetailSerializer,
    InvoiceEventSerializer,
    InvoiceListSerializer,
    InvoiceUpdateSerializer,
    NoteSerializer,
    VoidSerializer,
)
from ..services import alerts as alert_service
from ..services import bulk as bulk_service
from ..services import invoices as service

ADMIN = [IsAuthenticated, IsBillingAdmin]


class InvoiceViewSet(viewsets.GenericViewSet):
    """No destroy, no PUT. There is no endpoint that deletes an invoice, and a
    PUT would invite a client to send a whole object including `status`."""

    permission_classes = [IsAuthenticated, IsSubscriptionMember]
    pagination_class = DefaultPagination
    filterset_class = InvoiceFilterSet
    serializer_class = InvoiceListSerializer

    def get_queryset(self):
        qs = annotate_invoice_flags(visible_invoices(self.request.user))
        if self.action in {"retrieve", "partial_update"}:
            qs = qs.prefetch_related("credit_notes__created_by", "events__actor")
        return qs

    def filter_queryset(self, qs):
        params = self.request.query_params
        qs = InvoiceFilterSet(params, queryset=qs, request=self.request).qs
        key = params.get("ordering")
        return qs.order_by(*INVOICE_ORDERING.get(key, DEFAULT_INVOICE_ORDERING))

    def _detail(self, invoice):
        obj = self.get_queryset().get(pk=invoice.pk)
        return InvoiceDetailSerializer(
            obj, context=self.get_serializer_context()
        ).data

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        data = InvoiceListSerializer(
            page, many=True, context=self.get_serializer_context()
        ).data
        return self.get_paginated_response(data)

    def retrieve(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, obj)
        return Response(self._detail(obj))

    def create(self, request):
        s = InvoiceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        subscription = get_object_or_404(
            visible_subscriptions(request.user), pk=data.pop("subscription_id")
        )
        invoice = service.create_invoice(
            subscription=subscription, actor=request.user, **data
        )
        return Response(self._detail(invoice), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, obj)
        s = InvoiceUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        invoice = service.edit_invoice(obj, actor=request.user, **s.validated_data)
        return Response(self._detail(invoice))

    # --- lifecycle: billing admin only (Goals 1, 4) -------------------------

    @action(detail=True, methods=["post"], permission_classes=ADMIN)
    def issue(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        invoice = service.transition(obj, InvoiceStatus.ISSUED, request.user)
        return Response(self._detail(invoice))

    @action(detail=True, methods=["post"], permission_classes=ADMIN)
    def pay(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        invoice = service.transition(obj, InvoiceStatus.PAID, request.user)
        return Response(self._detail(invoice))

    @action(detail=True, methods=["post"], permission_classes=ADMIN)
    def void(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        s = VoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        invoice = service.transition(
            obj, InvoiceStatus.VOID, request.user, reason=s.validated_data["reason"]
        )
        return Response(self._detail(invoice))

    @action(
        detail=True,
        methods=["post"],
        url_path="credit-notes",
        permission_classes=ADMIN,
    )
    def credit_notes(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        s = CreditNoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        credit_note = service.add_credit_note(
            obj,
            amount=s.validated_data["amount"],
            reason=s.validated_data["reason"],
            actor=request.user,
        )
        return Response(
            CreditNoteSerializer(credit_note).data, status=status.HTTP_201_CREATED
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="dismiss-alert",
        permission_classes=ADMIN,
    )
    def dismiss_alert(self, request, pk=None):
        invoice = alert_service.dismiss(pk, request.user)
        return Response({"dismissed_for_due_date": invoice.due_date})

    # --- notes and timeline (Goal 9) ----------------------------------------

    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, obj)
        s = NoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        event = service.add_note(obj, request.user, s.validated_data["text"])
        return Response(
            InvoiceEventSerializer(event).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, obj)
        qs = obj.events.select_related("actor").order_by("created_at")
        return Response(InvoiceEventSerializer(qs, many=True).data)


class BulkGenerateView(APIView):
    """Goal 7. Declared before the router in urls.py, or the router's detail
    route would try to parse "bulk-generate" as an invoice UUID."""

    permission_classes = ADMIN

    def post(self, request):
        s = BulkGenerateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        report = bulk_service.bulk_generate(
            request.user, s.validated_data.get("as_of")
        )
        return Response(report)
