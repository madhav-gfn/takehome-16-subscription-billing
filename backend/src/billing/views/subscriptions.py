from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..enums import InvoiceStatus
from ..filters import (
    DEFAULT_SUBSCRIPTION_ORDERING,
    SUBSCRIPTION_ORDERING,
    SubscriptionFilterSet,
)
from ..pagination import DefaultPagination
from ..permissions import IsBillingAdmin, IsSubscriptionMember
from ..querysets import visible_subscriptions
from ..serializers import (
    CollaboratorCreateSerializer,
    SubscriptionCreateSerializer,
    SubscriptionDetailSerializer,
    SubscriptionSerializer,
    SubscriptionUpdateSerializer,
)
from ..services import subscriptions as service

ZERO = Value(
    Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2)
)


class SubscriptionViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsSubscriptionMember]
    pagination_class = DefaultPagination
    filterset_class = SubscriptionFilterSet
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        qs = visible_subscriptions(self.request.user).prefetch_related(
            "collaborators__user"
        )
        if self.action == "list":
            # One annotated aggregate rather than a query per row.
            qs = qs.annotate(
                inv_total=Count("invoices", distinct=True),
                inv_draft=Count(
                    "invoices",
                    filter=Q(invoices__status=InvoiceStatus.DRAFT),
                    distinct=True,
                ),
                inv_issued=Count(
                    "invoices",
                    filter=Q(invoices__status=InvoiceStatus.ISSUED),
                    distinct=True,
                ),
                inv_paid=Count(
                    "invoices",
                    filter=Q(invoices__status=InvoiceStatus.PAID),
                    distinct=True,
                ),
                inv_void=Count(
                    "invoices",
                    filter=Q(invoices__status=InvoiceStatus.VOID),
                    distinct=True,
                ),
                inv_outstanding=Coalesce(
                    Sum(
                        "invoices__amount",
                        filter=Q(invoices__status=InvoiceStatus.ISSUED),
                    ),
                    ZERO,
                ),
            )
        return qs

    def filter_queryset(self, qs):
        params = self.request.query_params
        if "archived" not in params:
            # Default: an unfiltered list shows active work.
            qs = qs.filter(archived_at__isnull=True)
        qs = SubscriptionFilterSet(params, queryset=qs, request=self.request).qs
        key = params.get("ordering")
        return qs.order_by(
            *SUBSCRIPTION_ORDERING.get(key, DEFAULT_SUBSCRIPTION_ORDERING)
        )

    def list(self, request):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        data = SubscriptionSerializer(
            page, many=True, context=self.get_serializer_context()
        ).data
        return self.get_paginated_response(data)

    def retrieve(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, obj)
        return Response(
            SubscriptionDetailSerializer(
                obj, context=self.get_serializer_context()
            ).data
        )

    def create(self, request):
        s = SubscriptionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = service.create_subscription(actor=request.user, **s.validated_data)
        return Response(
            SubscriptionDetailSerializer(
                obj, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        self.check_object_permissions(request, obj)
        s = SubscriptionUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        obj = service.update_subscription(
            obj, actor=request.user, **s.validated_data
        )
        return Response(
            SubscriptionDetailSerializer(
                obj, context=self.get_serializer_context()
            ).data
        )

    # --- billing admin only (Goals 2, 5) ------------------------------------

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsBillingAdmin],
    )
    def archive(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        obj = service.archive(obj, actor=request.user)
        return Response(
            SubscriptionDetailSerializer(
                obj, context=self.get_serializer_context()
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsBillingAdmin],
    )
    def restore(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        obj = service.restore(obj, actor=request.user)
        return Response(
            SubscriptionDetailSerializer(
                obj, context=self.get_serializer_context()
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsBillingAdmin],
    )
    def collaborators(self, request, pk=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        s = CollaboratorCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        service.add_collaborator(
            obj, user_id=s.validated_data["user_id"], actor=request.user
        )
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(
            SubscriptionDetailSerializer(
                obj, context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"collaborators/(?P<user_id>[^/.]+)",
        permission_classes=[IsAuthenticated, IsBillingAdmin],
    )
    def remove_collaborator(self, request, pk=None, user_id=None):
        obj = get_object_or_404(self.get_queryset(), pk=pk)
        deleted = service.remove_collaborator(obj, user_id=user_id)
        if not deleted:
            from django.http import Http404

            raise Http404
        return Response(status=status.HTTP_204_NO_CONTENT)
