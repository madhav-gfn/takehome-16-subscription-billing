"""DRF permission classes — the "is this role allowed to attempt this at all"
layer.

Object-state legality lives in services/, and row visibility lives in RLS.
Keeping the three separate is what stops a rule ending up in two places with
two different answers.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from src.accounts.models import Role


class IsBillingAdmin(BasePermission):
    message = (
        "Only a billing admin can issue, mark paid, void or credit-note an "
        "invoice, archive a subscription, manage collaborators, or run bulk "
        "generation."
    )

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and user.role == Role.BILLING_ADMIN
        )


class IsSubscriptionMember(BasePermission):
    """Object-level: billing admin, owner, or collaborator.

    Rarely reached, because the querysets already 404 a stranger. It exists so
    a view that forgets to scope its queryset still fails closed.
    """

    message = "You do not own or collaborate on this subscription."

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == Role.BILLING_ADMIN:
            return True
        subscription = obj if hasattr(obj, "owner_id") else obj.subscription
        return (
            subscription.owner_id == user.id
            or subscription.collaborators.filter(user_id=user.id).exists()
        )


class ReadOnlyOrBillingAdmin(BasePermission):
    message = "Only a billing admin can change this."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            request.method in SAFE_METHODS or user.role == Role.BILLING_ADMIN
        )
