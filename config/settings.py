"""Django settings for the OpenForum MVP.

Everything security-sensitive is read from environment variables so the same
image can run locally (DEBUG=1) and on a public host (DEBUG=0).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Tiny .env loader (no external dependency). Real env vars always win.
# ---------------------------------------------------------------------------
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default=None):
    value = os.environ.get(name)
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-me"
    else:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is required when DJANGO_DEBUG=0. "
            "Generate one with: python -c \"import secrets;print(secrets.token_urlsafe(50))\""
        )

ALLOWED_HOSTS = env_list(
    "DJANGO_ALLOWED_HOSTS",
    ["localhost", "127.0.0.1", "[::1]"] if DEBUG else [],
)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

SITE_NAME = env("SITE_NAME", "OpenForum")
SITE_URL = env("SITE_URL", "http://localhost:8000").rstrip("/")
SITE_TAGLINE = env("SITE_TAGLINE", "A place to ask, share and build together.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "community",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "community.middleware.RateLimitMiddleware",
    "community.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "community.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database: SQLite by default (zero cost, single file under ./data).
# Set POSTGRES_HOST to switch to PostgreSQL without touching code.
# ---------------------------------------------------------------------------
if env("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": env("POSTGRES_HOST"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "NAME": env("POSTGRES_DB", "forum"),
            "USER": env("POSTGRES_USER", "forum"),
            "PASSWORD": env("POSTGRES_PASSWORD", ""),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "data" / "db.sqlite3",
            "OPTIONS": {"timeout": 20},
        }
    }

# Database-backed cache keeps rate limits correct across gunicorn workers.
# `manage.py createcachetable` is run by the container entrypoint.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "forum_cache",
    }
}
if "test" in os.sys.argv or env("DJANGO_CACHE") == "locmem":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "forum-locmem",
        }
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = ["community.auth_backends.EmailOrUsernameBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("zh-hans", "简体中文"),
    ("ja", "日本語"),
    ("es", "Español"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGE_COOKIE_NAME = "forum_language"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# Static files (served by WhiteNoise, no extra web server required)
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Email / account activation
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", f"{SITE_NAME} <no-reply@example.com>")
EMAIL_VERIFICATION_TTL_HOURS = int(env("EMAIL_VERIFICATION_TTL_HOURS", "48"))

# ---------------------------------------------------------------------------
# Anti-abuse: CAPTCHA + rate limits
# ---------------------------------------------------------------------------
# none | turnstile | recaptcha
CAPTCHA_PROVIDER = env("CAPTCHA_PROVIDER", "none").lower()
TURNSTILE_SITE_KEY = env("TURNSTILE_SITE_KEY")
TURNSTILE_SECRET_KEY = env("TURNSTILE_SECRET_KEY")
RECAPTCHA_SITE_KEY = env("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = env("RECAPTCHA_SECRET_KEY")

# Only enable behind a reverse proxy you control (e.g. Caddy).
TRUST_X_FORWARDED_FOR = env_bool("TRUST_X_FORWARDED_FOR", False)

# Minimum seconds between rendering a form and submitting it (bot speed bump).
FORM_MIN_FILL_SECONDS = 2

# ---------------------------------------------------------------------------
# Legal placeholders
# ---------------------------------------------------------------------------
LEGAL_EFFECTIVE_DATE = env("LEGAL_EFFECTIVE_DATE", "2026-01-01")
LEGAL_CONTACT_EMAIL = env("LEGAL_CONTACT_EMAIL", "legal@example.com")
LEGAL_COMPANY = env("LEGAL_COMPANY", "OpenForum Labs (placeholder entity)")
LEGAL_JURISDICTION = env("LEGAL_JURISDICTION", "your jurisdiction")

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
DATA_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "community": {"handlers": ["console"], "level": "INFO"},
        "django.security": {"handlers": ["console"], "level": "WARNING"},
    },
}
