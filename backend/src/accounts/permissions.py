"""
DRF Permission Classes for RBAC
================================

These permission classes enforce role-based access at the application layer.
They work alongside (not instead of) PostgreSQL RLS policies.

Usage in views:
    class MyView(APIView):
        permission_classes = [IsAuthenticated, IsBillingAdmin]

    class SubscriptionDetailView(APIView):
        permission_classes = [IsAuthenticated, IsOwnerOrCollaboratorOrAdmin]
"""

from rest_framework.permissions import BasePermission


class IsBillingAdmin(BasePermission):
    """
    Allows access only to users with the billing_admin role.
    Returns a descriptive error message on denial.
    """

    message = (
        "This action requires the Billing Admin role. "
        "Account Managers are not permitted to perform this operation."
    )

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "billing_admin"
        )


class IsAccountManager(BasePermission):
    """
    Allows access only to users with the account_manager role.
    """

    message = "This action requires the Account Manager role."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "account_manager"
        )


class IsBillingAdminOrReadOnly(BasePermission):
    """
    Billing admins get full access; everyone else gets read-only.
    Useful for endpoints where account managers can view but not modify.
    """

    message = "Only Billing Admins can modify this resource."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user and request.user.is_authenticated
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "billing_admin"
        )


# IsOwnerOrCollaboratorOrAdmin and CanManageInvoiceLifecycle previously lived
# here. They referenced a billing app that did not exist yet and silently
# returned False on LookupError, which fails closed but invisibly. They are
# superseded by src.billing.permissions, next to the models they guard.
