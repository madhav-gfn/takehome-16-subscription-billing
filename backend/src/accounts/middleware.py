"""
RLS Transaction Middleware
==========================

This middleware is the bridge between JWT authentication and PostgreSQL
Row-Level Security. It provides defense-in-depth: even if application-level
authorization (DRF permissions, decorators) is bypassed due to a bug,
RLS policies at the database tier will still block unauthorized access.

Architecture:
    Request → JWTAuthMiddleware (parse token) → RLSTransactionMiddleware
    → DRF view (authentication + permissions + DB queries under RLS)

The middleware:
1. Parses the JWT from the Authorization header (lightweight decode, no DB query).
2. Wraps the entire request in a database transaction (transaction.atomic).
3. Executes SET LOCAL app.user_id and SET LOCAL app.role inside that transaction.
4. All subsequent DB queries within the request see RLS-filtered data.
5. On transaction end (commit or rollback), SET LOCAL values are discarded —
   safe for connection pooling (PgBouncer in transaction mode, Django CONN_MAX_AGE).

Why SET LOCAL (not SET):
    SET LOCAL is scoped to the current transaction. When the transaction ends,
    the variable resets. This prevents state leakage across requests sharing
    a pooled connection. SET (without LOCAL) persists for the entire session,
    which is dangerous with connection pooling.
"""

import logging

from django.db import connection, transaction
from rest_framework_simplejwt.tokens import AccessToken, TokenError

logger = logging.getLogger(__name__)


class RLSTransactionMiddleware:
    """
    Wraps every request in a DB transaction with RLS session variables set.

    Must be placed AFTER CorsMiddleware/SecurityMiddleware/CommonMiddleware
    and BEFORE any middleware that accesses the database.

    For unauthenticated requests (no token or invalid token), sets
    app.role = 'anonymous' — RLS policies should deny all access for this role.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id, role = self._extract_jwt_claims(request)

        # Store parsed claims on request for use by views/permissions
        # (DRF's simplejwt auth will also set request.user independently)
        request.rls_user_id = user_id or ""
        request.rls_role = role or "anonymous"

        # Skip RLS for non-PostgreSQL backends (e.g., SQLite in tests)
        if connection.vendor != "postgresql":
            return self.get_response(request)

        # Wrap the entire request lifecycle in a transaction with RLS vars
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SET LOCAL app.user_id = %s", [str(user_id or "")]
                    )
                    cursor.execute(
                        "SET LOCAL app.role = %s", [role or "anonymous"]
                    )

                response = self.get_response(request)

                # Roll back on server errors to prevent partial writes
                if response.status_code >= 500:
                    transaction.set_rollback(True)

            return response
        except Exception:
            logger.exception("RLSTransactionMiddleware: unhandled exception")
            raise

    @staticmethod
    def _extract_jwt_claims(request):
        """
        Lightweight JWT decode to extract user_id and role.
        Uses simplejwt's AccessToken class for validation.
        Returns (user_id, role) or (None, None) on any failure.
        """
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None, None

        token_str = auth_header[7:]
        try:
            token = AccessToken(token_str)
            user_id = str(token.get("user_id", ""))
            role = token.get("role", "")
            return user_id, role
        except TokenError:
            return None, None
        except Exception:
            logger.warning(
                "RLSTransactionMiddleware: unexpected error decoding JWT",
                exc_info=True,
            )
            return None, None
