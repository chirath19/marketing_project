"""Configuration guards.

The brief rules certain dependencies and behaviours out of this version.
A test is the only thing that keeps that true six months from now.
"""

import importlib
from pathlib import Path

import pytest
from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR)
SETTINGS_MODULES = ["config.settings.base", "config.settings.dev",
                    "config.settings.prod", "config.settings.test"]

NETWORK_MAIL_BACKENDS = ("smtp",)
FORBIDDEN_PACKAGES = ("redis", "celery", "django-celery", "kombu",
                      "django-anymail", "sendgrid", "twilio", "boto3")


# --- no outbound messaging -------------------------------------------------


def test_the_configured_mailer_cannot_reach_the_network():
    """This version sends nothing outbound. Every message is persisted and
    shown in the in-app Inbox instead."""
    backend = settings.MAILERS["default"]["BACKEND"]

    assert not any(name in backend for name in NETWORK_MAIL_BACKENDS), backend


@pytest.mark.parametrize("module_path", SETTINGS_MODULES)
def test_no_settings_module_configures_an_smtp_mailer(module_path):
    module = importlib.import_module(module_path)
    mailers = getattr(module, "MAILERS", {})

    for alias, config in mailers.items():
        assert "smtp" not in config["BACKEND"], f"{module_path}:{alias}"


def test_no_forbidden_runtime_dependency_is_declared():
    lines = (BASE_DIR / "requirements" / "base.txt").read_text().lower().splitlines()
    # Comments explain why these are absent, so only requirement lines count.
    declared = [
        line.split("==")[0].split("[")[0].strip()
        for line in lines
        if line.strip() and not line.strip().startswith(("#", "-r"))
    ]

    for package in FORBIDDEN_PACKAGES:
        assert package not in declared, f"{package} must not be a dependency"


def test_no_forbidden_package_is_importable_as_a_configured_app():
    for app in settings.INSTALLED_APPS:
        assert not app.startswith(("redis", "celery", "django_celery")), app


def test_the_cache_is_not_redis():
    """Redis is explicitly out of scope; the cache is database-backed."""
    backend = settings.CACHES["default"]["BACKEND"]

    assert "redis" not in backend.lower()


# --- no credentials in source ---------------------------------------------


def test_the_secret_key_is_not_the_startproject_default():
    assert not settings.SECRET_KEY.startswith("django-insecure-")


def test_no_settings_file_hardcodes_a_secret_key():
    for path in (BASE_DIR / "config" / "settings").glob("*.py"):
        text = path.read_text()
        assert 'SECRET_KEY = "' not in text, path.name
        assert "SECRET_KEY = '" not in text, path.name


def test_the_env_template_contains_no_real_credentials():
    template = (BASE_DIR / ".env.example").read_text()

    assert "DJANGO_SECRET_KEY=replace-me" in template
    assert "CLOUDINARY_API_SECRET=\n" in template or "CLOUDINARY_API_SECRET=" in template


def test_the_real_env_file_is_ignored_by_git():
    ignored = (BASE_DIR / ".gitignore").read_text()

    assert "\n.env\n" in ignored
    assert "!.env.example" in ignored


# --- security posture ------------------------------------------------------


def test_production_settings_refuse_debug():
    module = importlib.import_module("config.settings.prod")

    assert module.DEBUG is False


def test_production_settings_force_secure_cookies():
    module = importlib.import_module("config.settings.prod")

    assert module.SESSION_COOKIE_SECURE is True
    assert module.CSRF_COOKIE_SECURE is True
    assert module.SECURE_HSTS_SECONDS > 0
    assert module.X_FRAME_OPTIONS == "DENY"


def test_the_api_denies_unauthenticated_access_by_default():
    """Deny-first: a new viewset is closed until it opts out."""
    defaults = settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]

    assert defaults == ["rest_framework.permissions.IsAuthenticated"]


def test_the_api_is_paginated_by_default():
    assert settings.REST_FRAMEWORK["PAGE_SIZE"] > 0
    assert settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]


# --- database --------------------------------------------------------------


def test_postgresql_is_the_database():
    assert "postgresql" in settings.DATABASES["default"]["ENGINE"]
