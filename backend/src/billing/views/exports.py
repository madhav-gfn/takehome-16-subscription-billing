import csv
from datetime import date

from django.http import StreamingHttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from ..enums import InvoiceStatus
from ..filters import InvoiceFilterSet
from ..querysets import annotate_invoice_flags, visible_invoices

HEADERS = [
    "invoice_id", "customer_name", "billing_email", "plan_name", "owner_email",
    "period_start", "period_end", "amount", "due_date", "days_overdue", "status",
]


class _Echo:
    """csv.writer needs a file-like object; this one just returns the line."""

    def write(self, value):
        return value


class ReceivablesCSVView(APIView):
    """Goal 7. Every Issued invoice — overdue ones included, since they are
    still owed. Accepts the same filters as the invoice list, so "export what
    I am looking at" works and the two can never drift apart."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = annotate_invoice_flags(visible_invoices(request.user)).filter(
            status=InvoiceStatus.ISSUED
        )
        qs = InvoiceFilterSet(request.query_params, queryset=qs, request=request).qs
        qs = qs.select_related("subscription", "subscription__owner").order_by(
            "due_date"
        )

        writer = csv.writer(_Echo())

        def rows():
            yield writer.writerow(HEADERS)
            for invoice in qs.iterator(chunk_size=500):
                yield writer.writerow(
                    [
                        invoice.id,
                        invoice.subscription.customer_name,
                        invoice.subscription.billing_email,
                        invoice.subscription.plan_name,
                        invoice.subscription.owner.email,
                        invoice.period_start,
                        invoice.period_end,
                        str(invoice.amount),  # str(Decimal), never %f
                        invoice.due_date,
                        invoice.days_overdue,
                        invoice.status,
                    ]
                )

        filename = f"receivables-{date.today()}.csv"
        response = StreamingHttpResponse(rows(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
