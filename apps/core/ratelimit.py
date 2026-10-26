"""Rate limiting.

Deliberately small and database-backed. The brief rules out Redis, and
the actions that need throttling here — registration, sign-in, and later
the public contact and quote forms — are low-volume enough that counting
rows in an indexed window is the right trade.

Usage from a view or service::

    from apps.core.ratelimit import REGISTRATION_IP, check

    verdict = check(REGISTRATION_IP, client_ip(request))
    if not verdict.allowed:
        ...  # tell the caller to try again later

`check` records the attempt as a side effect, so a caller cannot forget
to. Use `peek` where you need the verdict without spending an attempt.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone


@dataclass(frozen=True, slots=True)
class RateLimit:
    scope: str
    limit: int
    window: timedelta

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("A rate limit must allow at least one attempt.")


@dataclass(frozen=True, slots=True)
class Verdict:
    allowed: bool
    remaining: int
    retry_after: timedelta | None


# The configured limits. Registration is throttled by address because a
# single abuser is the threat; sign-in is throttled by both address and
# account, so that one noisy network cannot lock out an unrelated user and
# a distributed attempt on one account is still caught.
REGISTRATION_IP = RateLimit("registration:ip", limit=5, window=timedelta(hours=1))
LOGIN_IP = RateLimit("login:ip", limit=20, window=timedelta(minutes=15))
LOGIN_ACCOUNT = RateLimit("login:account", limit=10, window=timedelta(minutes=15))


def hash_key(value: str) -> str:
    """Salted hash of an identifier.

    Keyed with SECRET_KEY so the digests cannot be reversed from a leaked
    backup with a rainbow table of email addresses.
    """
    return hmac.new(
        settings.SECRET_KEY.encode(),
        (value or "").strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()


def client_ip(request: HttpRequest) -> str:
    """The caller's address.

    `X-Forwarded-For` is trusted only when the deployment says a proxy is
    in front — otherwise any client could spoof the header and reset its
    own throttle. On Railway that is true; locally it is not.
    """
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            # The left-most entry is the original client; the rest were
            # appended by proxies along the way.
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _window_start(limit: RateLimit):
    return timezone.now() - limit.window


def peek(limit: RateLimit, key: str) -> Verdict:
    """The verdict without recording an attempt."""
    from apps.core.models import RateLimitEvent

    hashed = hash_key(key)
    since = _window_start(limit)

    events = RateLimitEvent.objects.filter(
        scope=limit.scope, key=hashed, created_at__gte=since
    ).order_by("created_at")

    used = events.count()
    if used < limit.limit:
        return Verdict(allowed=True, remaining=limit.limit - used, retry_after=None)

    oldest = events.first()
    retry_after = (oldest.created_at + limit.window) - timezone.now() if oldest else limit.window
    return Verdict(allowed=False, remaining=0,
                   retry_after=max(retry_after, timedelta(seconds=1)))


def record(limit: RateLimit, key: str) -> None:
    from apps.core.models import RateLimitEvent

    RateLimitEvent.objects.create(scope=limit.scope, key=hash_key(key))


def check(limit: RateLimit, key: str) -> Verdict:
    """Record an attempt and return whether it is permitted.

    The attempt is recorded even when it is refused: a caller that keeps
    hammering should keep extending its own lockout rather than getting a
    free retry the moment the window edges forward.
    """
    verdict = peek(limit, key)
    record(limit, key)
    return verdict


def reset(limit: RateLimit, key: str) -> None:
    """Clear a key's attempts — used after a successful sign-in."""
    from apps.core.models import RateLimitEvent

    RateLimitEvent.objects.filter(scope=limit.scope, key=hash_key(key)).delete()
