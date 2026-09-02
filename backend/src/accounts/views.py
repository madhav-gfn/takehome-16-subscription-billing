from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/login/

    Authenticates a user with email + password and returns JWT tokens
    with custom claims (role, email) embedded in the payload.

    Request body:
        {"email": "...", "password": "..."}

    Response 200:
        {"access": "<jwt>", "refresh": "<jwt>"}

    Response 401:
        {"detail": "No active account found with the given credentials"}
    """

    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(APIView):
    """
    POST /api/auth/register/

    Creates a new user account and returns JWT tokens.

    Request body:
        {"email": "...", "password": "...", "role": "billing_admin|account_manager"}

    Response 201:
        {"user": {...}, "tokens": {"access": "...", "refresh": "..."}}

    Response 400:
        {"email": ["user with this email already exists."], ...}
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate tokens for the newly created user
        token_serializer = CustomTokenObtainPairSerializer()
        tokens = token_serializer.get_token(user)

        return Response(
            {
                "user": UserSerializer(user).data,
                "tokens": {
                    "access": str(tokens.access_token),
                    "refresh": str(tokens),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    """
    GET /api/auth/me/

    Returns the authenticated user's profile.
    Requires a valid JWT access token in the Authorization header.

    Response 200:
        {"id": "...", "email": "...", "role": "...", ...}

    Response 401:
        {"detail": "Authentication credentials were not provided."}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserListView(APIView):
    """
    GET /api/auth/users/?role=account_manager

    A minimal directory: id, email and role only. Needed to populate the owner
    picker (Goal 2), the collaborator picker (Goal 5) and the filter-by-owner
    control (Goal 6).

    Available to both roles: an account manager needs to see who owns what in
    order to use the owner filter. It deliberately exposes nothing beyond the
    three fields the pickers need.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        User = get_user_model()
        users = User.objects.filter(is_active=True).order_by("email")
        role = request.query_params.get("role")
        if role:
            users = users.filter(role=role)
        return Response(
            [
                {"id": str(u.id), "email": u.email, "role": u.role}
                for u in users
            ]
        )
