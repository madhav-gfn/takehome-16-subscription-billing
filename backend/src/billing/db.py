"""Running database work outside a request.

FORCE ROW LEVEL SECURITY applies to the table owner, which is the user Django
connects as. Inside a request, RLSTransactionMiddleware sets app.role and
app.user_id. Outside one — management commands, data migrations, tests — those
variables are unset, current_setting(..., true) returns NULL, every policy
evaluates falsy, and the command silently reads and writes nothing.

Silently. That is the whole reason this module exists.
"""

from contextlib import contextmanager

from django.db import connection, transaction


@contextmanager
def rls_session(role, user_id=""):
    """Set the RLS session variables for a block of work, as a request would.

    Usage:
        with rls_session("billing_admin", admin.id):
            ...
    """
    if connection.vendor != "postgresql":
        # SQLite test runs have no RLS to configure.
        yield
        return

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.role = %s", [role or "anonymous"])
            cursor.execute("SET LOCAL app.user_id = %s", [str(user_id or "")])
        yield
