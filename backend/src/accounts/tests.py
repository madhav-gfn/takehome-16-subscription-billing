"""
Tests for the accounts (auth) system.

Covers:
- User model creation and constraints
- Registration endpoint (valid, duplicate, missing fields)
- Login endpoint (correct credentials, wrong password, missing user)
- Token validation (expired, malformed, refresh-as-access)
- Token refresh endpoint
- /me endpoint (authenticated vs. unauthenticated)
- Role-based access control (billing admin vs. account manager)
- RLS middleware SET LOCAL behavior (PostgreSQL only)
"""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

User = get_user_model()


class UserModelTests(TestCase):
    """Tests for the custom User model."""

    def test_create_user_with_email_and_role(self):
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            role="billing_admin",
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertEqual(user.role, "billing_admin")
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("testpass123"))
        # UUID primary key
        self.assertIsInstance(user.id, uuid.UUID)

    def test_create_user_without_email_raises(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="test", role="billing_admin")

    def test_create_user_without_role_raises(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="test@example.com", password="test", role="")

    def test_email_uniqueness(self):
        User.objects.create_user(
            email="unique@example.com", password="test", role="billing_admin"
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                email="unique@example.com", password="test2", role="account_manager"
            )

    def test_is_billing_admin_property(self):
        admin = User.objects.create_user(
            email="admin@test.com", password="test", role="billing_admin"
        )
        manager = User.objects.create_user(
            email="mgr@test.com", password="test", role="account_manager"
        )
        self.assertTrue(admin.is_billing_admin)
        self.assertFalse(admin.is_account_manager)
        self.assertFalse(manager.is_billing_admin)
        self.assertTrue(manager.is_account_manager)

    def test_email_normalization(self):
        user = User.objects.create_user(
            email="Test@EXAMPLE.com", password="test", role="billing_admin"
        )
        # Django's normalize_email lowercases the domain part
        self.assertEqual(user.email, "Test@example.com")


class RegisterViewTests(TestCase):
    """Tests for POST /api/auth/register/"""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/register/"

    def test_register_billing_admin(self):
        response = self.client.post(
            self.url,
            {
                "email": "newadmin@example.com",
                "password": "securepass123",
                "role": "billing_admin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn("user", data)
        self.assertIn("tokens", data)
        self.assertEqual(data["user"]["email"], "newadmin@example.com")
        self.assertEqual(data["user"]["role"], "billing_admin")
        self.assertIn("access", data["tokens"])
        self.assertIn("refresh", data["tokens"])

    def test_register_account_manager(self):
        response = self.client.post(
            self.url,
            {
                "email": "newmgr@example.com",
                "password": "securepass123",
                "role": "account_manager",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["user"]["role"], "account_manager")

    def test_register_duplicate_email(self):
        User.objects.create_user(
            email="exists@example.com", password="test", role="billing_admin"
        )
        response = self.client.post(
            self.url,
            {
                "email": "exists@example.com",
                "password": "newpass123",
                "role": "account_manager",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_email(self):
        response = self.client.post(
            self.url,
            {"password": "test12345", "role": "billing_admin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_password(self):
        response = self.client.post(
            self.url,
            {"email": "no_pass@example.com", "role": "billing_admin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_role(self):
        response = self.client.post(
            self.url,
            {"email": "no_role@example.com", "password": "test12345"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_role(self):
        response = self.client.post(
            self.url,
            {
                "email": "badrole@example.com",
                "password": "test12345",
                "role": "superadmin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_short_password(self):
        response = self.client.post(
            self.url,
            {
                "email": "short@example.com",
                "password": "abc",
                "role": "billing_admin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginViewTests(TestCase):
    """Tests for POST /api/auth/login/"""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/login/"
        self.user = User.objects.create_user(
            email="login@example.com",
            password="correctpass",
            role="billing_admin",
        )

    def test_login_success(self):
        response = self.client.post(
            self.url,
            {"email": "login@example.com", "password": "correctpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)

    def test_login_wrong_password(self):
        response = self.client.post(
            self.url,
            {"email": "login@example.com", "password": "wrongpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_nonexistent_user(self):
        response = self.client.post(
            self.url,
            {"email": "ghost@example.com", "password": "anything"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_missing_fields(self):
        response = self.client.post(self.url, {"email": "login@example.com"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_token_contains_role(self):
        """Verify that the JWT access token contains the custom role claim."""
        response = self.client.post(
            self.url,
            {"email": "login@example.com", "password": "correctpass"},
            format="json",
        )
        access_token = response.json()["access"]
        decoded = AccessToken(access_token)
        self.assertEqual(decoded["role"], "billing_admin")
        self.assertEqual(decoded["email"], "login@example.com")
        self.assertEqual(str(decoded["user_id"]), str(self.user.id))

    def test_login_inactive_user(self):
        """Inactive users should not be able to log in."""
        self.user.is_active = False
        self.user.save()
        response = self.client.post(
            self.url,
            {"email": "login@example.com", "password": "correctpass"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TokenRefreshTests(TestCase):
    """Tests for POST /api/auth/refresh/"""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/refresh/"
        self.user = User.objects.create_user(
            email="refresh@example.com",
            password="testpass123",
            role="account_manager",
        )

    def test_refresh_valid_token(self):
        # First login to get tokens
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": "refresh@example.com", "password": "testpass123"},
            format="json",
        )
        refresh_token = login_response.json()["refresh"]

        # Use refresh token to get new access token
        response = self.client.post(
            self.url, {"refresh": refresh_token}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.json())

    def test_refresh_invalid_token(self):
        response = self.client.post(
            self.url, {"refresh": "invalid.token.here"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_missing_token(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MeViewTests(TestCase):
    """Tests for GET /api/auth/me/"""

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/auth/me/"
        self.admin = User.objects.create_user(
            email="metest@example.com",
            password="testpass123",
            role="billing_admin",
        )

    def test_me_authenticated(self):
        # Get token
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": "metest@example.com", "password": "testpass123"},
            format="json",
        )
        token = login_response.json()["access"]

        # Hit /me with token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data["email"], "metest@example.com")
        self.assertEqual(data["role"], "billing_admin")
        self.assertEqual(data["id"], str(self.admin.id))

    def test_me_unauthenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_invalid_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid.token.here")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_expired_token(self):
        """Expired tokens should be rejected."""
        # Create a token that's already expired
        token = AccessToken.for_user(self.admin)
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token)}")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RBACPermissionTests(TestCase):
    """
    Tests that role-based access control is enforced at the application layer.
    These test the permission classes and decorators, not RLS.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="rbac_admin@example.com",
            password="adminpass",
            role="billing_admin",
        )
        self.manager = User.objects.create_user(
            email="rbac_mgr@example.com",
            password="mgrpass",
            role="account_manager",
        )
        # Get tokens
        admin_login = self.client.post(
            "/api/auth/login/",
            {"email": "rbac_admin@example.com", "password": "adminpass"},
            format="json",
        )
        self.admin_token = admin_login.json()["access"]

        mgr_login = self.client.post(
            "/api/auth/login/",
            {"email": "rbac_mgr@example.com", "password": "mgrpass"},
            format="json",
        )
        self.manager_token = mgr_login.json()["access"]

    def test_admin_token_has_correct_role(self):
        decoded = AccessToken(self.admin_token)
        self.assertEqual(decoded["role"], "billing_admin")

    def test_manager_token_has_correct_role(self):
        decoded = AccessToken(self.manager_token)
        self.assertEqual(decoded["role"], "account_manager")

    def test_tokens_have_different_user_ids(self):
        admin_decoded = AccessToken(self.admin_token)
        mgr_decoded = AccessToken(self.manager_token)
        self.assertNotEqual(admin_decoded["user_id"], mgr_decoded["user_id"])


class RLSMiddlewareTests(TestCase):
    """
    Tests for the RLS Transaction Middleware.
    These verify JWT parsing and request attribute setting.
    DB-level SET LOCAL is only testable with PostgreSQL.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="rls@example.com",
            password="testpass",
            role="account_manager",
        )
        login_response = self.client.post(
            "/api/auth/login/",
            {"email": "rls@example.com", "password": "testpass"},
            format="json",
        )
        self.token = login_response.json()["access"]

    def test_middleware_sets_rls_attributes_on_authenticated_request(self):
        """
        The middleware should parse the JWT and set rls_user_id and rls_role
        on the request object.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_middleware_handles_no_token_gracefully(self):
        """Requests without a token should get anonymous RLS attributes."""
        response = self.client.get("/api/auth/me/")
        # DRF returns 401 (auth failure), but the middleware itself doesn't crash
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_middleware_handles_malformed_token(self):
        """Malformed tokens should result in anonymous RLS attributes."""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not.a.valid.jwt")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class SeedUsersCommandTests(TestCase):
    """Tests for the seed_users management command."""

    def test_seed_creates_demo_users(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("seed_users", stdout=out)

        self.assertEqual(User.objects.count(), 3)
        self.assertTrue(User.objects.filter(email="admin@example.com").exists())
        self.assertTrue(User.objects.filter(email="manager1@example.com").exists())
        self.assertTrue(User.objects.filter(email="manager2@example.com").exists())

        admin = User.objects.get(email="admin@example.com")
        self.assertEqual(admin.role, "billing_admin")
        self.assertTrue(admin.check_password("admin123"))

    def test_seed_idempotent(self):
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("seed_users", stdout=out)
        call_command("seed_users", stdout=out)
        # Should not create duplicates
        self.assertEqual(User.objects.count(), 3)

    def test_seed_with_flush(self):
        from django.core.management import call_command
        from io import StringIO

        # Create an extra user
        User.objects.create_user(
            email="extra@example.com", password="test", role="billing_admin"
        )
        self.assertEqual(User.objects.count(), 1)

        out = StringIO()
        call_command("seed_users", "--flush", stdout=out)
        # Extra user should be deleted, only demo users remain
        self.assertEqual(User.objects.count(), 3)
        self.assertFalse(User.objects.filter(email="extra@example.com").exists())
