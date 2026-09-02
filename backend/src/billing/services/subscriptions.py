"""Subscription rules (Goals 2, 5)."""

from django.db import transaction
from django.utils import timezone

from src.accounts.models import Role, User

from ..errors import (
    AlreadyArchived,
    AlreadyCollaborator,
    CollaboratorMustBeAM,
    NotArchived,
    OwnerCannotBeCollaborator,
    OwnerChangeAdminOnly,
    OwnerMustBeAccountManager,
    OwnerMustBeSelf,
    SubscriptionArchived,
)
from ..models import Collaborator, Subscription

EDITABLE_FIELDS = {
    "customer_name",
    "billing_email",
    "plan_name",
    "billing_cycle",
    "price",
    "start_date",
}


def _resolve_owner(owner_id, actor):
    """Ruling A-01: an AM may only create subscriptions they own; a BA may name
    any account manager. Ruling A-02: the owner is always an account manager."""
    if actor.role != Role.BILLING_ADMIN:
        if owner_id and str(owner_id) != str(actor.id):
            raise OwnerMustBeSelf()
        return actor

    if not owner_id:
        raise OwnerMustBeAccountManager()
    owner = User.objects.filter(pk=owner_id).first()
    if owner is None or owner.role != Role.ACCOUNT_MANAGER:
        raise OwnerMustBeAccountManager()
    return owner


@transaction.atomic
def create_subscription(*, actor, owner_id=None, **fields):
    owner = _resolve_owner(owner_id, actor)
    return Subscription.objects.create(owner=owner, **fields)


@transaction.atomic
def update_subscription(subscription, *, actor, owner_id=None, **changes):
    # Ruling A-16: editing a stopped arrangement has no meaning and invites
    # confusion about whether it will resume billing. Restore first.
    if subscription.is_archived:
        raise SubscriptionArchived()

    if owner_id and str(owner_id) != str(subscription.owner_id):
        if actor.role != Role.BILLING_ADMIN:
            raise OwnerChangeAdminOnly()
        subscription.owner = _resolve_owner(owner_id, actor)

    applied = []
    for field, value in changes.items():
        if field in EDITABLE_FIELDS and value is not None:
            setattr(subscription, field, value)
            applied.append(field)

    subscription.save()
    return subscription


@transaction.atomic
def archive(subscription, *, actor):
    """Stops future invoices without destroying invoice history (Goal 2)."""
    if subscription.is_archived:
        raise AlreadyArchived()
    subscription.archived_at = timezone.now()
    subscription.save(update_fields=["archived_at", "updated_at"])
    return subscription


@transaction.atomic
def restore(subscription, *, actor):
    if not subscription.is_archived:
        raise NotArchived()
    subscription.archived_at = None
    subscription.save(update_fields=["archived_at", "updated_at"])
    return subscription


@transaction.atomic
def add_collaborator(subscription, *, user_id, actor):
    """Goal 5. Billing admin only — enforced by the view's permission class and
    again by the collaborators RLS policy."""
    user = User.objects.filter(pk=user_id).first()
    if user is None or user.role != Role.ACCOUNT_MANAGER:
        raise CollaboratorMustBeAM()
    if str(user.id) == str(subscription.owner_id):
        raise OwnerCannotBeCollaborator()
    if subscription.collaborators.filter(user_id=user.id).exists():
        raise AlreadyCollaborator()

    return Collaborator.objects.create(
        subscription=subscription, user=user, added_by=actor
    )


@transaction.atomic
def remove_collaborator(subscription, *, user_id):
    deleted, _ = subscription.collaborators.filter(user_id=user_id).delete()
    return deleted
