from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..services import alerts as service


class AlertListView(APIView):
    """Goal 10."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        results = service.list_alerts(request.user)
        return Response({"count": len(results), "results": results})


class AlertCountView(APIView):
    """The nav badge. A dedicated endpoint so the badge does not pull the whole
    list; both call the same queryset, so they cannot disagree."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"count": service.count_alerts(request.user)})
