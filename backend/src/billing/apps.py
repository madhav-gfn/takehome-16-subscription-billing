from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.billing"
    # Explicit: RLS policies, migrations and cross-app model lookups all refer
    # to this label. Letting Django infer it from the dotted path is fragile.
    label = "billing"
    verbose_name = "Billing"
