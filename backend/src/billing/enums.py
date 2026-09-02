from django.db import models


class BillingCycle(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    ANNUAL = "annual", "Annual"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


# Lifecycle order for ?ordering=status. Explicit, because alphabetical order
# matching lifecycle order here is a coincidence, not a property to rely on.
STATUS_SORT_ORDER = {
    InvoiceStatus.DRAFT: 0,
    InvoiceStatus.ISSUED: 1,
    InvoiceStatus.PAID: 2,
    InvoiceStatus.VOID: 3,
}

# The only legal moves. Anything absent from this map is rejected with a 409.
ALLOWED_TRANSITIONS = {
    InvoiceStatus.DRAFT: {InvoiceStatus.ISSUED, InvoiceStatus.VOID},
    InvoiceStatus.ISSUED: {InvoiceStatus.PAID, InvoiceStatus.VOID},
    InvoiceStatus.PAID: set(),
    InvoiceStatus.VOID: set(),
}

# Statuses whose rows are frozen entirely.
TERMINAL_STATUSES = {InvoiceStatus.PAID, InvoiceStatus.VOID}


class EventType(models.TextChoices):
    CREATED = "created", "Created"
    STATUS_CHANGED = "status_changed", "Status changed"
    VOIDED = "voided", "Voided"
    FIELD_CHANGED = "field_changed", "Field changed"
    CREDIT_NOTE_ISSUED = "credit_note_issued", "Credit note issued"
    NOTE_ADDED = "note_added", "Note added"
