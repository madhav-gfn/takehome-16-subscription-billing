from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views.alerts import AlertCountView, AlertListView
from .views.dashboard import DashboardView
from .views.exports import ReceivablesCSVView
from .views.invoices import BulkGenerateView, InvoiceViewSet
from .views.subscriptions import SubscriptionViewSet

router = DefaultRouter()
router.register("subscriptions", SubscriptionViewSet, basename="subscription")
router.register("invoices", InvoiceViewSet, basename="invoice")

urlpatterns = [
    # Declared BEFORE the router: its detail route matches invoices/<pk>/, and
    # without this Django would try to resolve "bulk-generate" as a UUID.
    path("invoices/bulk-generate/", BulkGenerateView.as_view(), name="bulk-generate"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("alerts/", AlertListView.as_view(), name="alerts"),
    path("alerts/count/", AlertCountView.as_view(), name="alert-count"),
    path("exports/receivables.csv", ReceivablesCSVView.as_view(), name="receivables"),
    path("", include(router.urls)),
]
