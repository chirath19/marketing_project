"""Settings for the automated test suite."""

from .base import *  # noqa: F403
from .base import MIDDLEWARE

DEBUG = False

# Nothing is served from disk under test.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

# Fast, deterministic hashing — tests create a lot of users.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}

# Captured in memory so a stray send is assertable instead of printed.
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"},
}

LOGGING["root"]["level"] = "CRITICAL"  # noqa: F405
