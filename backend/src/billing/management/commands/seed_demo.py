"""Seed the demo dataset (doc2/09-seed-data-plan.md).

Every date is relative to today. A seed with hardcoded dates looks broken three
months later: nothing overdue, an empty 8-week chart, a dashboard of zeros.

Wrapped in rls_session("billing_admin", ...) throughout. Without it, FORCE ROW
LEVEL SECURITY denies every insert and this command reports success having
written nothing.
"""

import random
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from src.accounts.models import Role, User
from src.billing.db import rls_session
from src.billing.enums import EventType, InvoiceStatus
from src.billing.models import (
    AlertDismissal,
    Collaborator,
    CreditNote,
    Invoice,
    InvoiceEvent,
    Subscription,
)
from src.billing.periods import due_date_for, period_for_index

USERS = [
    ("admin@example.com", "admin123", Role.BILLING_ADMIN),
    ("manager1@example.com", "manager123", Role.ACCOUNT_MANAGER),
    ("manager2@example.com", "manager123", Role.ACCOUNT_MANAGER),
    # Deliberately NOT published in SUBMISSION.md. It owns subscriptions that
    # manager1 and manager2 cannot see, so that logging in as manager1 visibly
    # does not show everything — the observable proof of Goal 1.
    ("manager3@example.com", "manager123", Role.ACCOUNT_MANAGER),
]

# (customer, plan, cycle, price, months_ago, owner_idx, collaborator_idxs, flags)
# owner/collaborator indexes are into MANAGERS (m1, m2, m3).
SUBSCRIPTIONS = [
    ("Northwind Traders",     "Pro",        "monthly",  "199.00",  8, 0, [1], {}),
    ("Contoso Ltd",           "Enterprise", "monthly",  "899.00",  6, 0, [1, 2], {"overdue": True}),
    ("Fabrikam Inc",          "Starter",    "monthly",   "49.00",  5, 0, [],  {"overdue": True, "draft": True}),
    ("Adventure Works",       "Pro",        "annual",  "1990.00", 14, 0, [],  {}),
    ("Tailwind Traders",      "Starter",    "monthly",   "49.00",  4, 1, [0], {"void": True}),
    ("Woodgrove Bank",        "Enterprise", "annual",  "8990.00", 10, 1, [],  {"overdue": True, "credit": "400.00"}),
    ("Litware Inc",           "Pro",        "monthly",  "199.00",  3, 1, [],  {"overdue": True}),
    ("Proseware",             "Starter",    "monthly",   "49.00",  7, 1, [0], {"archive_months": 1}),
    ("Wide World Importers",  "Pro",        "monthly",  "199.00",  9, 0, [],  {"overdue": True, "chronic": True}),
    ("Lucerne Publishing",    "Starter",    "monthly",   "49.00",  2, 0, [1], {"draft": True}),
    ("Alpine Ski House",      "Enterprise", "monthly",  "899.00",  5, 2, [],  {}),
    ("Relecloud",             "Pro",        "monthly",  "199.00",  4, 2, [],  {"draft": True}),
    ("Trey Research",         "Starter",    "monthly",   "49.00",  6, 2, [0], {}),
    ("Blue Yonder Airlines",  "Pro",        "monthly",  "199.00", -1, 1, [],  {}),  # starts next month
]


class Command(BaseCommand):
    help = "Seed a demo dataset covering every screen."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true",
                            help="Delete all billing data and users first.")
        parser.add_argument("--force", action="store_true",
                            help="Allow --flush when DEBUG is False.")

    def handle(self, *args, **options):
        random.seed(42)  # deterministic: two runs produce identical data
        self.today = timezone.localdate()

        if options["flush"]:
            self._flush(options["force"])

        admin = self._seed_users()
        with rls_session(Role.BILLING_ADMIN, admin.id):
            self._seed_subscriptions(admin)
        self._report()

    # ------------------------------------------------------------------ flush
    def _flush(self, force):
        from django.conf import settings

        if not settings.DEBUG and not force:
            self.stderr.write(self.style.ERROR(
                "Refusing to flush with DEBUG=False. Pass --force if you are "
                "certain — this deletes the deployed demo data."))
            raise SystemExit(1)

        admin = User.objects.filter(role=Role.BILLING_ADMIN).first()
        with rls_session(Role.BILLING_ADMIN, admin.id if admin else ""):
            # FK order. Events and credit notes have append-only triggers on
            # UPDATE/DELETE, so they are dropped by raw SQL below instead.
            from django.db import connection

            with connection.cursor() as cur:
                if connection.vendor == "postgresql":
                    cur.execute("ALTER TABLE invoice_events DISABLE TRIGGER trg_events_append_only")
                    cur.execute("ALTER TABLE credit_notes DISABLE TRIGGER trg_credit_notes_append_only")
            InvoiceEvent.objects.all().delete()
            CreditNote.objects.all().delete()
            AlertDismissal.objects.all().delete()
            Invoice.objects.all().delete()
            Collaborator.objects.all().delete()
            Subscription.objects.all().delete()
            with connection.cursor() as cur:
                if connection.vendor == "postgresql":
                    cur.execute("ALTER TABLE invoice_events ENABLE TRIGGER trg_events_append_only")
                    cur.execute("ALTER TABLE credit_notes ENABLE TRIGGER trg_credit_notes_append_only")
        User.objects.all().delete()
        self.stdout.write(self.style.WARNING("Flushed all billing data and users."))

    # ------------------------------------------------------------------ users
    def _seed_users(self):
        self.users = {}
        for email, password, role in USERS:
            user, created = User.objects.get_or_create(
                email=email, defaults={"role": role})
            if created:
                user.set_password(password)
                user.save()
            self.users[email] = user
        self.managers = [
            self.users["manager1@example.com"],
            self.users["manager2@example.com"],
            self.users["manager3@example.com"],
        ]
        return self.users["admin@example.com"]

    # ---------------------------------------------------------- subscriptions
    def _seed_subscriptions(self, admin):
        for (name, plan, cycle, price, months_ago, owner_idx,
             collab_idxs, flags) in SUBSCRIPTIONS:
            if Subscription.objects.filter(customer_name=name).exists():
                continue

            start = self.today - relativedelta(months=months_ago)
            sub = Subscription.objects.create(
                customer_name=name,
                billing_email=f"ap@{name.split()[0].lower()}.test",
                plan_name=plan,
                billing_cycle=cycle,
                price=Decimal(price),
                start_date=start,
                owner=self.managers[owner_idx],
                archived_at=(
                    timezone.now() - relativedelta(months=flags["archive_months"])
                    if "archive_months" in flags else None
                ),
            )
            for idx in collab_idxs:
                Collaborator.objects.create(
                    subscription=sub, user=self.managers[idx], added_by=admin)

            self._seed_invoices(sub, admin, flags)

    # --------------------------------------------------------------- invoices
    def _seed_invoices(self, sub, admin, flags):
        if sub.start_date > self.today:
            return  # Blue Yonder — bulk-generate will report it as skipped

        # Walk every period from start_date to today.
        periods = []
        n = 0
        while True:
            start, end = period_for_index(sub.start_date, sub.billing_cycle, n)
            if start > self.today:
                break
            periods.append((start, end))
            n += 1
            if n > 40:
                break

        total = len(periods)
        for i, (start, end) in enumerate(periods):
            age = total - 1 - i  # 0 == current period
            invoice = Invoice.objects.create(
                subscription=sub, period_start=start, period_end=end,
                amount=sub.price, due_date=due_date_for(start),
                status=InvoiceStatus.DRAFT, created_by=sub.owner,
            )
            self._event(invoice, EventType.CREATED, sub.owner,
                        amount=str(sub.price), source="bulk")

            if age == 0 and flags.get("draft"):
                continue  # leave the current period as a draft

            # Issue everything that is not a deliberate draft.
            self._advance(invoice, InvoiceStatus.ISSUED, admin,
                          when=start + timedelta(days=1))

            if age >= 2:
                # Older periods are settled.
                paid_on = invoice.due_date + timedelta(days=random.randint(-3, 4))
                self._advance(invoice, InvoiceStatus.PAID, admin, when=paid_on)
            elif age == 1 and flags.get("overdue"):
                pass  # left issued and past due -> alerts
            elif age == 1:
                self._advance(invoice, InvoiceStatus.PAID, admin,
                              when=invoice.due_date - timedelta(days=1))

        self._apply_flavour(sub, admin, flags)

    def _advance(self, invoice, target, actor, when):
        old = invoice.status
        invoice.status = target
        if target == InvoiceStatus.ISSUED:
            invoice.issued_at = self._aware(when)
        elif target == InvoiceStatus.PAID:
            invoice.paid_at = self._aware(when)
        invoice.save()
        self._event(invoice, EventType.STATUS_CHANGED, actor,
                    old_status=old, new_status=target, at=when)

    def _apply_flavour(self, sub, admin, flags):
        """The exceptions that make each screen show something."""
        invoices = list(sub.invoices.order_by("period_start"))
        if not invoices:
            return

        if flags.get("void") and len(invoices) >= 2:
            target = invoices[-2]
            target.status = InvoiceStatus.VOID
            target.void_reason = "Billed at the wrong plan tier"
            target.save()
            self._event(target, EventType.STATUS_CHANGED, admin,
                        old_status="issued", new_status="void")
            self._event(target, EventType.VOIDED, admin,
                        reason=target.void_reason)
            # A-14: the void frees the period, so a corrected invoice exists.
            Invoice.objects.create(
                subscription=sub, period_start=target.period_start,
                period_end=target.period_end, amount=sub.price,
                due_date=target.due_date, status=InvoiceStatus.ISSUED,
                issued_at=timezone.now(), created_by=admin)

        if flags.get("credit"):
            paid = sub.invoices.filter(status=InvoiceStatus.PAID).last()
            if paid:
                cn = CreditNote.objects.create(
                    invoice=paid, amount=Decimal(flags["credit"]),
                    reason="Service credit for downtime in this period",
                    created_by=admin)
                self._event(paid, EventType.CREDIT_NOTE_ISSUED, admin,
                            credit_note_id=str(cn.id), amount=str(cn.amount),
                            reason=cn.reason)

        overdue = sub.invoices.filter(
            status=InvoiceStatus.ISSUED, due_date__lt=self.today).first()

        if flags.get("chronic") and overdue:
            # The A-10 case, live in the demo: dismissed against an old due
            # date, then the due date moved and passed again -> alert is back.
            AlertDismissal.objects.update_or_create(
                invoice=overdue,
                defaults={
                    "dismissed_for_due_date": overdue.due_date - timedelta(days=10),
                    "dismissed_by": admin,
                })
            self._event(overdue, EventType.NOTE_ADDED, admin,
                        text="Extended after the customer's AP contact went on leave")

        # Two dismissals that are still in force, so the badge shows fewer
        # alerts than there are overdue invoices.
        if sub.customer_name in {"Contoso Ltd"} and overdue:
            AlertDismissal.objects.update_or_create(
                invoice=overdue,
                defaults={"dismissed_for_due_date": overdue.due_date,
                          "dismissed_by": admin})

        # The reference specimen: six event types on one invoice.
        if sub.customer_name == "Northwind Traders":
            paid = sub.invoices.filter(status=InvoiceStatus.PAID).last()
            if paid:
                cn = CreditNote.objects.create(
                    invoice=paid, amount=Decimal("50.00"),
                    reason="Overbilled one seat", created_by=admin)
                self._event(paid, EventType.CREDIT_NOTE_ISSUED, admin,
                            credit_note_id=str(cn.id), amount="50.00",
                            reason=cn.reason)
                self._event(paid, EventType.NOTE_ADDED, sub.owner,
                            text="Customer asked for a PO number on the next one")
                self._event(paid, EventType.NOTE_ADDED, admin,
                            text="Confirmed payment by BACS, ref 88213")

    def _event(self, invoice, event_type, actor, *, old_status=None,
               new_status=None, at=None, **details):
        return InvoiceEvent.objects.create(
            invoice=invoice, event_type=event_type, actor=actor,
            old_status=old_status, new_status=new_status, details=details)

    @staticmethod
    def _aware(value):
        if hasattr(value, "hour"):
            return value
        return timezone.make_aware(
            timezone.datetime.combine(value, timezone.datetime.min.time()))

    # ----------------------------------------------------------------- report
    def _report(self):
        from src.billing.querysets import active_alerts

        admin = self.users["admin@example.com"]
        counts = {
            "users": User.objects.count(),
            "subscriptions": Subscription.objects.count(),
            "collaborators": Collaborator.objects.count(),
            "invoices": Invoice.objects.count(),
            "credit notes": CreditNote.objects.count(),
            "events": InvoiceEvent.objects.count(),
            "dismissals": AlertDismissal.objects.count(),
        }
        self.stdout.write("")
        for label, n in counts.items():
            self.stdout.write(f"  {label:>15}: {n}")

        with rls_session(Role.BILLING_ADMIN, admin.id):
            overdue = Invoice.objects.filter(
                status=InvoiceStatus.ISSUED, due_date__lt=self.today).count()
            alerting = active_alerts(admin, self.today).count()
        self.stdout.write(f"  {'overdue':>15}: {overdue}")
        self.stdout.write(f"  {'alerting':>15}: {alerting}  (badge count)")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo credentials:"))
        for email, password, role in USERS[:3]:
            self.stdout.write(f"  {role:<16} {email:<24} {password}")
        self.stdout.write(self.style.NOTICE(
            "  (manager3@example.com / manager123 exists but is intentionally "
            "unpublished — it proves account-manager scoping.)"))
