"""Abstract bases shared by every domain.

Concrete models belong to their own domain app. Nothing here creates a
table.
"""

import uuid

from django.db import models


class TimeStampedModel(models.Model):
    """Creation and modification timestamps, indexed for list ordering.

    `created_at` carries an index because every dashboard list in the
    product is ordered by recency.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class UUIDPrimaryKeyModel(models.Model):
    """A non-enumerable primary key.

    Used for anything whose identifier is exposed in a URL a client can
    see, so that record counts and other tenants' volumes cannot be
    inferred by walking integers.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class RateLimitEvent(models.Model):
    """One recorded attempt at a throttled action.

    Why a table rather than the cache: the configured cache is the
    database anyway (Redis is out of scope), and `DatabaseCache.incr` is a
    read-then-write without a lock, so two simultaneous requests can both
    read the same count and a limit of five can let six through. Counting
    committed rows has no such race.

    It also makes abuse visible — staff can see that a burst happened —
    and it is trivially purgeable. `purge_rate_limit_events` does that;
    rows outside every configured window have no value.

    `key` holds a salted hash, never a raw address or email. This table is
    a throttle, not an audit log: it needs to recognise a repeat caller,
    not identify one. The audit app records who did what.
    """

    scope = models.CharField(max_length=32)
    key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "rate limit event"
        indexes = [
            # The only query this table serves: count recent rows for one
            # scope and key. Ordering the composite this way lets a single
            # index range-scan satisfy it.
            models.Index(fields=["scope", "key", "created_at"],
                         name="ratelimit_lookup_idx"),
            models.Index(fields=["created_at"], name="ratelimit_purge_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key[:8]}… at {self.created_at:%Y-%m-%d %H:%M}"


class OperatingSettings(TimeStampedModel):
    """One owner-managed operating mode. Existing integration data is preserved."""

    integrations_enabled = models.BooleanField(default=False)
    api_enabled = models.BooleanField(default=False)
    analytics_enabled = models.BooleanField(default=False)
    show_public_prices = models.BooleanField(default=False)
    require_quote_account = models.BooleanField(default=False)
    feature_flags = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return "Operating settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
