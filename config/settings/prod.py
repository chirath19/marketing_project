"""Production settings (Railway).

Everything here is driven by environment variables. The deploy fails fast
rather than starting in an insecure half-configured state.
"""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Railway terminates TLS at the edge and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Railway's edge sets X-Forwarded-For, so it can be used to identify a
# caller for rate limiting. Locally it cannot — see TRUST_PROXY_HEADERS.
TRUST_PROXY_HEADERS = env.bool("DJANGO_TRUST_PROXY_HEADERS", default=True)
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)

# Railway's healthcheck prober hits the container directly over plain
# HTTP, with no X-Forwarded-Proto header — it never goes through the
# edge that real traffic does. Without this, the redirect above turns
# every health check into a 301 and the deploy never goes healthy.
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_AGE = env.int("DJANGO_SESSION_COOKIE_AGE", default=60 * 60 * 12)

SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Nothing may leave the platform by email in this version. Enquiries,
# quote requests, approvals and system alerts are persisted and surfaced
# in the in-app Inbox and Notification Center instead.
MAILERS = {
    "default": {"BACKEND": "django.core.mail.backends.dummy.EmailBackend"},
}

# `mail.E001` exists to catch a deploy that forgot to configure SMTP. Here
# the absence of a sending backend is the requirement, not an oversight,
# so the check is silenced explicitly rather than worked around. When an
# email provider is added later, delete this line first — the check should
# start failing again until the provider is configured properly.
SILENCED_SYSTEM_CHECKS = ["mail.E001"]
