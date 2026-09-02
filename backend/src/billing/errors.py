"""Domain errors and the DRF exception handler.

Every failure the API can produce renders through one envelope:
    {"error": {"code": ..., "message": ..., "field": ..., "details": {...}}}

`code` is stable and machine-readable. `message` is written for a human and is
what the UI shows verbatim — the client never writes its own explanation for a
rule it does not own.
"""

import logging
import re

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db.utils import InternalError
from django.http import Http404
from rest_framework import status as http
from rest_framework.exceptions import (
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """A business rule refused the action."""

    code = "DOMAIN_ERROR"
    http_status = http.HTTP_409_CONFLICT
    message = "This action is not allowed."

    def __init__(self, message=None, *, field=None, **details):
        self.message = message or self.message
        self.field = field
        self.details = details
        super().__init__(self.message)


# --- Invoice lifecycle (Goal 4) ---------------------------------------------


class InvalidTransition(DomainError):
    code = "INVALID_TRANSITION"

    def __init__(self, current, target):
        hint = ""
        if current == "draft" and target == "paid":
            hint = " An invoice must be issued before it can be marked paid."
        super().__init__(
            f"An invoice that is {current} cannot be marked {target}.{hint}",
            current_status=current,
            target_status=target,
        )


class InvoicePaidImmutable(DomainError):
    code = "INVOICE_PAID_IMMUTABLE"
    message = (
        "This invoice is paid and cannot be changed. "
        "Issue a credit note to correct it."
    )


class InvoicePaidCannotVoid(DomainError):
    code = "INVOICE_PAID_CANNOT_VOID"
    message = (
        "This invoice has been paid and cannot be voided. "
        "Issue a credit note against it instead."
    )


class InvoiceIssuedLocked(DomainError):
    code = "INVOICE_ISSUED_LOCKED"
    message = (
        "This invoice has been issued, so its billing period and amount are "
        "locked. You can still change its due date."
    )


class InvoiceVoidTerminal(DomainError):
    code = "INVOICE_VOID_IS_TERMINAL"
    message = "This invoice has been voided. Voided invoices cannot be changed."


class VoidReasonRequired(DomainError):
    code = "VOID_REASON_REQUIRED"
    http_status = http.HTTP_400_BAD_REQUEST
    message = "A reason is required when voiding an invoice."

    def __init__(self):
        super().__init__(field="reason")


class CreditNoteRequiresPaid(DomainError):
    code = "CREDIT_NOTE_REQUIRES_PAID"

    def __init__(self, current):
        super().__init__(
            f"Credit notes can only be issued against paid invoices. "
            f"This invoice is {current} — edit or void it instead.",
            current_status=current,
        )


class CreditExceedsInvoice(DomainError):
    code = "CREDIT_EXCEEDS_INVOICE"
    http_status = http.HTTP_400_BAD_REQUEST

    def __init__(self, amount, total, invoice_amount):
        super().__init__(
            f"A credit note of {amount} would bring total credits to {total}, "
            f"which is more than the invoice amount of {invoice_amount}.",
            field="amount",
            existing_total=str(total),
            invoice_amount=str(invoice_amount),
        )


class PeriodAlreadyInvoiced(DomainError):
    code = "PERIOD_ALREADY_INVOICED"

    def __init__(self, start, end, invoice_id=None):
        super().__init__(
            f"An invoice already exists for {start} - {end}.",
            existing_invoice_id=str(invoice_id) if invoice_id else None,
        )


# --- Subscriptions (Goals 2, 5) ---------------------------------------------


class SubscriptionArchived(DomainError):
    code = "SUBSCRIPTION_ARCHIVED"
    message = (
        "This subscription is archived. Restore it before making changes or "
        "creating invoices."
    )


class AlreadyArchived(DomainError):
    code = "ALREADY_ARCHIVED"
    message = "This subscription is already archived."


class NotArchived(DomainError):
    code = "NOT_ARCHIVED"
    message = "This subscription is not archived."


class OwnerMustBeSelf(DomainError):
    code = "SUBSCRIPTION_OWNER_MUST_BE_SELF"
    http_status = http.HTTP_403_FORBIDDEN
    message = (
        "Account managers can only create subscriptions they own. "
        "Ask a billing admin to assign a different owner."
    )


class OwnerChangeAdminOnly(DomainError):
    code = "OWNER_CHANGE_ADMIN_ONLY"
    http_status = http.HTTP_403_FORBIDDEN
    message = "Only a billing admin can change a subscription's owner."


class OwnerMustBeAccountManager(DomainError):
    code = "OWNER_MUST_BE_ACCOUNT_MANAGER"
    http_status = http.HTTP_400_BAD_REQUEST
    message = "A subscription must be owned by an account manager."


class CollaboratorMustBeAM(DomainError):
    code = "COLLABORATOR_MUST_BE_AM"
    http_status = http.HTTP_400_BAD_REQUEST
    message = "Only account managers can be added as collaborators."


class OwnerCannotBeCollaborator(DomainError):
    code = "OWNER_CANNOT_BE_COLLABORATOR"
    http_status = http.HTTP_400_BAD_REQUEST
    message = "This user already owns the subscription."


class AlreadyCollaborator(DomainError):
    code = "ALREADY_COLLABORATOR"
    message = "This user is already a collaborator on this subscription."


# --- Alerts (Goal 10) --------------------------------------------------------


class NotOverdue(DomainError):
    code = "NOT_OVERDUE"
    message = "This invoice is not overdue, so it has no alert to dismiss."


# --- Trigger backstop --------------------------------------------------------
# The service layer checks these conditions first and returns a clean 409. If a
# trigger fires it means a service check was missed, so the user still gets a
# correct answer and the miss is logged loudly.

TRIGGER_MAP = [
    (re.compile(r"is (paid|void) and immutable"), InvoicePaidImmutable),
    (re.compile(r"locked period and amount"), InvoiceIssuedLocked),
    (re.compile(r"append-only"), InvoicePaidImmutable),
    (re.compile(r"only a billing admin can archive"), OwnerChangeAdminOnly),
    (re.compile(r"only a billing admin can reassign"), OwnerChangeAdminOnly),
]


def _envelope(code, message, field=None, details=None, status_code=400):
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "field": field,
                "details": details or {},
            }
        },
        status=status_code,
    )


def exception_handler(exc, context):
    """Wired via REST_FRAMEWORK["EXCEPTION_HANDLER"]."""
    if isinstance(exc, DomainError):
        return _envelope(
            exc.code, exc.message, exc.field, exc.details, exc.http_status
        )

    if isinstance(exc, InternalError):
        text = str(exc)
        for pattern, error_class in TRIGGER_MAP:
            if pattern.search(text):
                logger.error(
                    "Database trigger fired - a service-layer check was "
                    "missed: %s",
                    text,
                )
                err = error_class()
                return _envelope(
                    err.code, err.message, None, {}, err.http_status
                )
        raise  # unknown InternalError - let it 500 loudly

    if isinstance(exc, Http404):
        # Same message whether the row is missing or merely invisible, so the
        # 404-not-403 choice is not undone by a chatty message.
        return _envelope(
            "NOT_FOUND",
            "Not found, or not visible to you.",
            status_code=http.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, NotAuthenticated):
        return _envelope(
            "UNAUTHENTICATED",
            str(getattr(exc, "detail", exc)),
            status_code=http.HTTP_401_UNAUTHORIZED,
        )

    if isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        return _envelope(
            "FORBIDDEN",
            str(getattr(exc, "detail", exc)),
            status_code=http.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, ValidationError):
        detail = exc.detail
        field, message = None, "Some fields are invalid."
        if isinstance(detail, dict) and detail:
            field = next(iter(detail))
            first = detail[field]
            message = str(first[0] if isinstance(first, list) else first)
        elif isinstance(detail, list) and detail:
            message = str(detail[0])
        return _envelope(
            "VALIDATION_ERROR",
            message,
            field,
            {"fields": detail},
            http.HTTP_400_BAD_REQUEST,
        )

    response = drf_default_handler(exc, context)
    if response is not None:
        data = response.data
        message = (
            str(data.get("detail", data)) if isinstance(data, dict) else str(data)
        )
        return _envelope("ERROR", message, status_code=response.status_code)
    return None
