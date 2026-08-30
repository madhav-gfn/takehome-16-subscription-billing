"""
Function-Based View Decorators for RBAC
========================================

These decorators are for use with Django function-based views (non-DRF).
For class-based DRF views, use the permission classes in permissions.py instead.

Usage:
    @login_required
    @billing_admin_required
    def my_admin_view(request):
        ...
"""

import functools

from django.http import JsonResponse


def login_required(view_func):
    """
    Rejects unauthenticated requests with HTTP 401.
    Checks for user_id set by RLSTransactionMiddleware's JWT parsing.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_id = getattr(request, "rls_user_id", None)
        if not user_id:
            return JsonResponse(
                {
                    "error": "Unauthorized",
                    "message": "Authentication credentials were not provided.",
                },
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def role_required(*allowed_roles):
    """
    Rejects requests from users whose role is not in allowed_roles.
    Returns HTTP 403 with an explanatory message.

    Usage:
        @role_required("billing_admin")
        def admin_only_view(request): ...

        @role_required("billing_admin", "account_manager")
        def any_authenticated_view(request): ...
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            role = getattr(request, "rls_role", None)
            if role not in allowed_roles:
                return JsonResponse(
                    {
                        "error": "Forbidden",
                        "message": (
                            f"This action requires one of the following roles: "
                            f"{', '.join(allowed_roles)}. "
                            f"Your current role ({role or 'anonymous'}) "
                            f"is not authorized."
                        ),
                    },
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def billing_admin_required(view_func):
    """
    Shorthand for @role_required("billing_admin").
    Used for invoice lifecycle transitions (issue, pay, void, credit-note)
    and subscription archiving.
    """
    return role_required("billing_admin")(view_func)
