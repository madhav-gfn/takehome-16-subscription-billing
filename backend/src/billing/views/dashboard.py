from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..services import dashboard as service


class DashboardView(APIView):
    """Goal 8. Figures are scoped to what the viewer can see, so an account
    manager gets their own book of business rather than the whole company."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(service.build(request.user))
