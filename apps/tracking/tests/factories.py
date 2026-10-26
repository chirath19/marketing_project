"""Test helpers for the agency website tracking domain."""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.tracking.models import AgencyWebsiteEvent

__all__ = ["make_event"]


def make_event(*, event_name: str = "page_view", occurred_at=None,  # noqa: ANN001
              **fields) -> AgencyWebsiteEvent:
    """An event, with `occurred_at` settable despite `auto_now_add`.

    `auto_now_add` ignores any value passed to `create()`, so a test
    that needs a specific date (to land inside or outside a range) has
    to set it with a follow-up `update()` instead. A bare `date` is
    placed at noon, server-local, so it never slips into the adjacent
    day once converted to a timezone-aware value.
    """
    event = AgencyWebsiteEvent.objects.create(event_name=event_name, **fields)
    if occurred_at is not None:
        if isinstance(occurred_at, dt.date) and not isinstance(occurred_at, dt.datetime):
            occurred_at = timezone.make_aware(
                dt.datetime.combine(occurred_at, dt.time(12, 0)))
        AgencyWebsiteEvent.objects.filter(pk=event.pk).update(occurred_at=occurred_at)
        event.refresh_from_db()
    return event
