"""
Management command to seed demo users for testing.

Usage:
    python main.py seed_users
    python main.py seed_users --flush  # Delete existing users first

Creates:
    - admin@example.com    (billing_admin)  password: admin123
    - manager1@example.com (account_manager) password: manager123
    - manager2@example.com (account_manager) password: manager123
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

DEMO_USERS = [
    {
        "email": "admin@example.com",
        "password": "admin123",
        "role": "billing_admin",
    },
    {
        "email": "manager1@example.com",
        "password": "manager123",
        "role": "account_manager",
    },
    {
        "email": "manager2@example.com",
        "password": "manager123",
        "role": "account_manager",
    },
]


class Command(BaseCommand):
    help = "Seed the database with demo users for each role."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing users before seeding.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            count = User.objects.count()
            User.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {count} existing users."))

        created_count = 0
        skipped_count = 0

        for user_data in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=user_data["email"],
                defaults={"role": user_data["role"]},
            )

            if created:
                user.set_password(user_data["password"])
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created {user.email} "
                        f"({user.get_role_display()}) "
                        f"[id: {user.id}]"
                    )
                )
                created_count += 1
            else:
                self.stdout.write(
                    self.style.NOTICE(
                        f"  Skipped {user.email} (already exists)"
                    )
                )
                skipped_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created_count}, Skipped: {skipped_count}"
            )
        )
        self.stdout.write("")
        self.stdout.write("Demo credentials:")
        self.stdout.write("-" * 60)
        for user_data in DEMO_USERS:
            self.stdout.write(
                f"  {user_data['role']:20s} | {user_data['email']:25s} | {user_data['password']}"
            )
