"""Trigram indexes for the Goal 6 substring search.

ILIKE '%term%' cannot use a B-tree. At a few hundred subscriptions a sequential
scan is fine — these exist because the brief asks what breaks at 100x, and this
is the honest answer for search.

Kept in its own migration because CREATE EXTENSION may need elevated rights on
a managed host. If it fails there, the schema is already in place and only the
index is lost; the query is unchanged.
"""

from django.db import migrations

FORWARD = r"""
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_sub_customer_trgm
    ON subscriptions USING gin (customer_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_sub_email_trgm
    ON subscriptions USING gin (billing_email gin_trgm_ops);
"""

REVERSE = r"""
DROP INDEX IF EXISTS idx_sub_email_trgm;
DROP INDEX IF EXISTS idx_sub_customer_trgm;
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_immutability")]

    operations = [migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE)]
