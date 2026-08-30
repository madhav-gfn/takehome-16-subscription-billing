import uuid

from django.contrib.auth.models import AbstractBaseUser
from django.db import models

from .managers import UserManager


class Role(models.TextChoices):
    """
    Two explicit roles as required by the spec.
    The values are stored in the DB and also set as PostgreSQL session
    variables via SET LOCAL for RLS policy evaluation.
    """

    BILLING_ADMIN = "billing_admin", "Billing Admin"
    ACCOUNT_MANAGER = "account_manager", "Account Manager"


class User(AbstractBaseUser):
    """
    Custom user model with UUID primary key and role-based access.

    - UUID PK is critical: RLS policies cast current_setting('app.user_id') to UUID.
    - No username field — email is the sole login identifier.
    - AbstractBaseUser provides password hashing (set_password / check_password)
      and last_login tracking.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        unique=True,
        db_index=True,
        max_length=255,
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # AbstractBaseUser config
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["role"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def is_billing_admin(self):
        return self.role == Role.BILLING_ADMIN

    @property
    def is_account_manager(self):
        return self.role == Role.ACCOUNT_MANAGER
