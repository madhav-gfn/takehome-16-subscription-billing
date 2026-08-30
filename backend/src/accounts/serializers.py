from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends simplejwt's default serializer to embed `role` and `email`
    directly in the JWT payload. This allows:
    1. The RLS middleware to read the role without a DB query.
    2. The frontend to display role-appropriate UI without a /me call.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Custom claims embedded in both access and refresh tokens
        token["role"] = user.role
        token["email"] = user.email
        return token


class RegisterSerializer(serializers.ModelSerializer):
    """
    Handles user registration with email, password, and role.
    Password is write-only and hashed via User.set_password().
    """

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
        error_messages={
            "min_length": "Password must be at least 8 characters long.",
        },
    )
    role = serializers.ChoiceField(
        choices=User.role.field.choices,
        error_messages={
            "invalid_choice": "Role must be 'billing_admin' or 'account_manager'.",
        },
    )

    class Meta:
        model = User
        fields = ["email", "password", "role"]

    def validate_email(self, value):
        """Normalize email to lowercase for consistent lookups."""
        return value.lower().strip()

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=validated_data["role"],
        )


class UserSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for user profile data returned by /me endpoint.
    """

    class Meta:
        model = User
        fields = ["id", "email", "role", "is_active", "created_at", "updated_at"]
        read_only_fields = fields
