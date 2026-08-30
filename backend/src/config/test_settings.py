"""
Test settings that override the database to use SQLite.
This allows running the auth test suite without a PostgreSQL connection.

The RLS middleware gracefully skips SET LOCAL for non-PostgreSQL backends.

Usage:
    python main.py test src.accounts --settings=src.config.test_settings
"""

from .settings import *  # noqa: F401, F403

# Override database to SQLite for tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
