from django.contrib.auth.models import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom manager for User model with email as the unique identifier.
    """

    def create_user(self, email, password=None, role=None, **extra_fields):
        """
        Create and return a regular user with an email, password, and role.
        """
        if not email:
            raise ValueError("Users must have an email address")
        if not role:
            raise ValueError("Users must have a role")

        email = self.normalize_email(email)
        user = self.model(email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, role=None, **extra_fields):
        """
        Create and return a superuser. Superusers are always billing_admin.
        """
        extra_fields.setdefault("is_active", True)
        role = role or "billing_admin"

        return self.create_user(email, password, role=role, **extra_fields)
