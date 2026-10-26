"""Settings shared by every environment.

Nothing secret lives in this file. Every value that differs between
machines, or that must never appear in source control, is read from the
environment — see `.env.example` for the full list.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = env("DJANGO_SECRET_KEY")

#: Encrypts provider credentials at rest — see `apps.core.fields`.
#: Blank in development; a key derived from `SECRET_KEY` is used
#: instead, which is not a substitute for a real one in any environment
#: holding a real provider token.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

ROOT_URLCONF = "config.urls"

# The admin is moved off the guessable default path. Obscurity is not a
# control on its own — it simply removes this install from the sweep of
# bots probing /admin/ — and the admin remains behind authentication.
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")

CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "accounts.User"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_htmx",
]

# Domain applications. Order is dependency-free: the modular monolith wires
# domains together through the core event bus, not through import order.
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.staff",
    "apps.permissions",
    "apps.cms",
    "apps.tracking",
    "apps.catalog",
    "apps.leads",
    "apps.subscriptions",
    "apps.campaigns",
    "apps.seo",
    "apps.paid_ads",
    "apps.social",
    "apps.email_marketing",
    "apps.analytics",
    "apps.approvals",
    "apps.messaging",
    "apps.notifications",
    "apps.media",
    "apps.integrations",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE = [
    "apps.core.operations.OperatingModeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    # After authentication: it resolves the current organization from the
    # signed-in user's memberships.
    "apps.organizations.middleware.CurrentOrganizationMiddleware",
]


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
                "apps.organizations.context_processors.organization",
                "apps.organizations.context_processors.portal_chrome",
                "apps.staff.context_processors.admin_navigation",
                "apps.cms.context_processors.site_chrome",
                "apps.tracking.context_processors.tracking_settings",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": env.db_url("DATABASE_URL"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DJANGO_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True


# ---------------------------------------------------------------------------
# Cache
#
# Database-backed on purpose. The brief rules out Redis for the initial
# version, and the cached surfaces here (navigation, site settings) are
# small and read-mostly. Create the table with `manage.py createcachetable`.
# ---------------------------------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "core_cache_table",
        "TIMEOUT": 300,
    },
}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

# One backend, not two. Django resolves `has_perm` as a union across
# backends, so leaving ModelBackend alongside this one would let a
# permission denied here be re-granted through a Django group — and a deny
# that something else can overturn is not a control. The backend subclasses
# ModelBackend, so authentication and the admin's own model permissions
# behave exactly as before.
AUTHENTICATION_BACKENDS = [
    "apps.permissions.backends.PlatformPermissionBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

# How a self-registered client account starts life.
#
#   "approval" — the account is PENDING until a staff member approves it.
#   "auto"     — the account is ACTIVE immediately.
#
# The default is approval. There is no email verification in this version,
# because nothing is sent outbound, so automatic activation would mean any
# address — real, mistyped or someone else's — gets a live account on an
# agency platform. Approval also matches how the business already works:
# a new client is scoped, priced and assigned an account manager before
# anything begins. The request lands in the staff Inbox alongside every
# other inbound message.
ACCOUNTS_REGISTRATION_MODE = env(
    "ACCOUNTS_REGISTRATION_MODE", default="approval"
)

if ACCOUNTS_REGISTRATION_MODE not in {"approval", "auto"}:
    raise ImproperlyConfigured(
        "ACCOUNTS_REGISTRATION_MODE must be 'approval' or 'auto', "
        f"not {ACCOUNTS_REGISTRATION_MODE!r}."
    )

# Whether X-Forwarded-For may be believed when identifying a caller for
# rate limiting. False locally: without a proxy in front, any client could
# set the header and reset its own throttle.
TRUST_PROXY_HEADERS = env.bool("DJANGO_TRUST_PROXY_HEADERS", default=False)

SESSION_COOKIE_NAME = "heliograph_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]


# ---------------------------------------------------------------------------
# Media
#
# `apps.media` owns the abstraction. The default backend writes to local
# disk; setting CLOUDINARY_URL (and MEDIA_BACKEND=cloudinary) swaps in the
# Cloudinary backend without any calling code changing.
# ---------------------------------------------------------------------------

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

MEDIA_BACKEND = env("MEDIA_BACKEND", default="local")

CLOUDINARY = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME", default=""),
    "API_KEY": env("CLOUDINARY_API_KEY", default=""),
    "API_SECRET": env("CLOUDINARY_API_SECRET", default=""),
    "SECURE": True,
    "FOLDER": env("CLOUDINARY_FOLDER", default="heliograph"),
}

_DEFAULT_FILE_STORAGE = {
    "local": "django.core.files.storage.FileSystemStorage",
    "cloudinary": "apps.media.storages.CloudinaryMediaStorage",
}[MEDIA_BACKEND]

STORAGES = {
    "default": {"BACKEND": _DEFAULT_FILE_STORAGE},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Mail
#
# The platform sends nothing outbound in this version. Every message —
# enquiry, quote, approval, system alert — is persisted and surfaced in the
# in-app Inbox and Notification Center. The console backend here exists so
# that any accidental `send_mail` call is visible in logs rather than
# delivered. Production uses the dummy backend, which discards.
# ---------------------------------------------------------------------------

MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"},
}


# ---------------------------------------------------------------------------
# Django REST Framework
#
# The API is a secondary surface: dashboards are server-rendered. Defaults
# are deny-first; each viewset opts in explicitly.
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
    },
}


# ---------------------------------------------------------------------------
# Site / brand defaults
#
# Overridable at runtime from the database (core.SystemSetting, added with
# the settings module in a later phase) so staff can edit without a deploy.
# ---------------------------------------------------------------------------

SITE_NAME = env("SITE_NAME", default="Heliograph")
SITE_TAGLINE = env("SITE_TAGLINE", default="Digital marketing agency")
SITE_CONTACT_EMAIL = env("SITE_CONTACT_EMAIL", default="hello@heliograph.agency")
SITE_DEFAULT_CURRENCY = env("SITE_DEFAULT_CURRENCY", default="USD")

# The browser chrome colour. A <meta> tag cannot read a CSS custom
# property, so this is the one place the brand navy has to exist outside
# the stylesheet; a test asserts the two stay equal.
SITE_THEME_COLOR = env("SITE_THEME_COLOR", default="#111C38")


# ---------------------------------------------------------------------------
# Logging
#
# Structured, single-line records on stdout — the format Railway collects.
# Application loggers live under the `apps` namespace.
# ---------------------------------------------------------------------------

LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logging.RequestIDFilter"},
    },
    "formatters": {
        "verbose": {
            "format": (
                "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s "
                "%(module)s:%(lineno)d — %(message)s"
            ),
        },
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
