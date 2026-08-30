import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _csv(value, default):
    if value is None:
        return default
    if isinstance(value, list):
        return value
    values = [item.strip() for item in str(value).split(",") if item.strip()]
    return values or default


# =============================================================================
# Core Settings
# =============================================================================

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = _csv(os.getenv("DJANGO_ALLOWED_HOSTS", "*"), ["*"])

# =============================================================================
# CORS
# =============================================================================

CORS_ALLOWED_ORIGINS = _csv(
    os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ),
    [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
)

CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# =============================================================================
# Application Definition
# =============================================================================

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    # Project apps
    "src.accounts",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    # RLS middleware: parses JWT → wraps request in DB transaction → SET LOCAL
    # Must be after CommonMiddleware and before any DB-accessing middleware.
    "src.accounts.middleware.RLSTransactionMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "src.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "src.config.wsgi.application"

# =============================================================================
# Custom User Model
# =============================================================================
# Must be set BEFORE the first migration. Uses UUID primary keys for RLS
# compatibility (current_setting('app.user_id')::UUID).

AUTH_USER_MODEL = "accounts.User"

# =============================================================================
# Database — PostgreSQL
# =============================================================================
# Connection pooling: CONN_MAX_AGE keeps connections alive for reuse.
# CONN_HEALTH_CHECKS validates connections before use (Django 4.1+).
# SET LOCAL is transaction-scoped, so connection reuse is safe.
#
# For production, use PgBouncer in transaction mode in front of PostgreSQL.
# PgBouncer config should use transaction pooling (pool_mode = transaction)
# to ensure SET LOCAL variables don't leak between requests.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "billing"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        # Connection pooling at the Django level
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "600")),
        "CONN_HEALTH_CHECKS": True,
    }
}

# =============================================================================
# Django REST Framework
# =============================================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
    ),
    # Consistent error responses
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
}

# =============================================================================
# Simple JWT Configuration
# =============================================================================

SIMPLE_JWT = {
    # Token lifetimes — access token is intentionally long-lived (user preference)
    "ACCESS_TOKEN_LIFETIME": timedelta(
        hours=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_HOURS", "24"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    ),
    # Rotation: issue a new refresh token when the old one is used
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    # Algorithm
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.getenv("JWT_SECRET_KEY", SECRET_KEY),
    # User identification
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    # Custom token serializer (adds role + email claims)
    "TOKEN_OBTAIN_SERIALIZER": "src.accounts.serializers.CustomTokenObtainPairSerializer",
    # Header format
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
}

# =============================================================================
# Password Validation
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
]

# =============================================================================
# Internationalization
# =============================================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# =============================================================================
# Static Files
# =============================================================================

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
