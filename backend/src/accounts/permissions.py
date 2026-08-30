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


class IsOwnerOrCollaboratorOrAdmin(BasePermission):
    """
    Object-level permission for subscription-scoped resources.

    - Billing admins: always allowed (global access).
    - Account managers: allowed only if they own or collaborate on the
      subscription associated with the object.

    The view must either:
    1. Set `self.subscription` on the view instance, OR
    2. The object itself must have an `owner_id` and be queryable against
       the collaborators table.

    This permission class checks object-level access. It requires the view
    to call `self.check_object_permissions(request, obj)` explicitly.
    """

    message = (
        "You do not own or collaborate on this subscription. "
        "Account Managers can only access subscriptions they own or collaborate on."
    )

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Billing admins have global access
        if user.role == "billing_admin":
            return True

        # For subscription objects directly
        if hasattr(obj, "owner_id"):
            if obj.owner_id == user.id:
                return True

            # Check collaborator table
            # Import here to avoid circular imports at module load time
            # (collaborator model will be in a billing app created later)
            from django.apps import apps

            try:
                Collaborator = apps.get_model("billing", "Collaborator")
                return Collaborator.objects.filter(
                    subscription_id=obj.id, user_id=user.id
                ).exists()
            except LookupError:
                # Collaborator model doesn't exist yet
                return False

        # For invoice objects (linked through subscription)
        if hasattr(obj, "subscription"):
            subscription = obj.subscription
            if subscription.owner_id == user.id:
                return True

            from django.apps import apps

            try:
                Collaborator = apps.get_model("billing", "Collaborator")
                return Collaborator.objects.filter(
                    subscription_id=subscription.id, user_id=user.id
                ).exists()
            except LookupError:
                return False

        return False


class CanManageInvoiceLifecycle(BasePermission):
    """
    Only Billing Admins can perform invoice lifecycle transitions:
    - Issue an invoice (Draft → Issued)
    - Mark as paid (Issued → Paid)
    - Void an invoice (Draft/Issued → Void)
    - Create a credit note (against a Paid invoice)

    Account Managers are explicitly prohibited from these operations,
    even on subscriptions they own.
    """

    message = (
        "Only Billing Admins can issue, mark as paid, void, or credit-note invoices. "
        "Account Managers can only create and edit draft invoices."
    )

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "billing_admin"
        )
