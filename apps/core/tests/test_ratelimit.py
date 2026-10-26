"""Rate limiting."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import RateLimitEvent
from apps.core.ratelimit import (
    RateLimit,
    check,
    client_ip,
    hash_key,
    peek,
    record,
    reset,
)

pytestmark = pytest.mark.django_db

LIMIT = RateLimit("test:scope", limit=3, window=timedelta(minutes=10))


def test_attempts_within_the_limit_are_allowed():
    for expected_remaining in (3, 2, 1):
        verdict = check(LIMIT, "someone")
        assert verdict.allowed
        assert verdict.remaining == expected_remaining


def test_the_attempt_after_the_limit_is_refused():
    for _ in range(3):
        check(LIMIT, "someone")

    verdict = check(LIMIT, "someone")

    assert not verdict.allowed
    assert verdict.remaining == 0


def test_a_refused_attempt_still_counts():
    """A caller that keeps hammering extends its own lockout rather than
    getting a free retry the moment the window edges forward."""
    for _ in range(5):
        check(LIMIT, "someone")

    assert RateLimitEvent.objects.filter(scope=LIMIT.scope).count() == 5


def test_keys_are_independent():
    for _ in range(3):
        check(LIMIT, "noisy")

    assert check(LIMIT, "quiet").allowed


def test_scopes_are_independent():
    other = RateLimit("test:other", limit=3, window=timedelta(minutes=10))
    for _ in range(3):
        check(LIMIT, "someone")

    assert check(other, "someone").allowed


def test_attempts_outside_the_window_do_not_count():
    for _ in range(3):
        record(LIMIT, "someone")

    RateLimitEvent.objects.update(created_at=timezone.now() - timedelta(minutes=11))

    assert peek(LIMIT, "someone").allowed


def test_the_refusal_says_how_long_to_wait():
    for _ in range(3):
        check(LIMIT, "someone")

    verdict = peek(LIMIT, "someone")

    assert verdict.retry_after is not None
    assert timedelta(0) < verdict.retry_after <= LIMIT.window


def test_peek_does_not_spend_an_attempt():
    peek(LIMIT, "someone")
    peek(LIMIT, "someone")

    assert RateLimitEvent.objects.count() == 0


def test_reset_clears_a_key():
    for _ in range(3):
        check(LIMIT, "someone")
    assert not peek(LIMIT, "someone").allowed

    reset(LIMIT, "someone")

    assert peek(LIMIT, "someone").allowed


def test_reset_leaves_other_keys_alone():
    check(LIMIT, "first")
    check(LIMIT, "second")

    reset(LIMIT, "first")

    assert RateLimitEvent.objects.count() == 1


# --- keys ------------------------------------------------------------------


def test_the_stored_key_is_a_hash_not_the_identifier():
    """The table is a throttle, not an audit log: it needs to recognise a
    repeat caller, not identify one."""
    record(LIMIT, "priya@vantage.example")
    stored = RateLimitEvent.objects.get().key

    assert "priya" not in stored
    assert "@" not in stored
    assert len(stored) == 64


def test_hashing_is_stable_and_case_insensitive():
    assert hash_key("Priya@Example.com") == hash_key("priya@example.com  ")


def test_different_identifiers_hash_differently():
    assert hash_key("a@example.com") != hash_key("b@example.com")


def test_the_hash_is_keyed_to_this_deployment(settings):
    """Keyed with SECRET_KEY, so digests from a leaked backup cannot be
    reversed with a precomputed table of email addresses."""
    first = hash_key("priya@example.com")
    settings.SECRET_KEY = "a-completely-different-secret-key-value"

    assert hash_key("priya@example.com") != first


# --- identifying the caller ------------------------------------------------


def test_the_forwarded_header_is_ignored_without_a_proxy(rf, settings):
    """Otherwise any client could set the header and reset its own
    throttle."""
    settings.TRUST_PROXY_HEADERS = False
    request = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.9", REMOTE_ADDR="10.0.0.1")

    assert client_ip(request) == "10.0.0.1"


def test_the_forwarded_header_is_used_behind_a_proxy(rf, settings):
    settings.TRUST_PROXY_HEADERS = True
    request = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.9, 10.0.0.2",
                     REMOTE_ADDR="10.0.0.1")

    assert client_ip(request) == "203.0.113.9"


def test_a_caller_with_no_address_still_gets_a_key(rf):
    request = rf.get("/")
    request.META.pop("REMOTE_ADDR", None)

    assert client_ip(request) == "unknown"


# --- configuration ---------------------------------------------------------


def test_a_limit_must_allow_at_least_one_attempt():
    with pytest.raises(ValueError, match="at least one"):
        RateLimit("broken", limit=0, window=timedelta(minutes=1))


# --- housekeeping ----------------------------------------------------------


def test_the_purge_command_removes_only_stale_rows():
    from django.core.management import call_command

    record(LIMIT, "recent")
    record(LIMIT, "old")
    RateLimitEvent.objects.filter(key=hash_key("old")).update(
        created_at=timezone.now() - timedelta(hours=72)
    )

    call_command("purge_rate_limit_events", hours=48, verbosity=0)

    assert RateLimitEvent.objects.count() == 1
    assert RateLimitEvent.objects.get().key == hash_key("recent")


def test_the_purge_command_can_be_rehearsed():
    from django.core.management import call_command

    record(LIMIT, "old")
    RateLimitEvent.objects.update(created_at=timezone.now() - timedelta(hours=72))

    call_command("purge_rate_limit_events", hours=48, dry_run=True, verbosity=0)

    assert RateLimitEvent.objects.count() == 1
