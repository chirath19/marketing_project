"""Recording agency website events.

Two ways an event gets written, and both end up here:

1. **From the browser**, through the consent-gated ingestion endpoint
   (`apps/tracking/views.py`), for events that only the browser can know
   happened — a page loaded, a service card was looked at.
2. **From the event bus**, for events that correspond to something this
   platform already recorded for its own reasons — a quote was actually
   submitted, a client actually registered. These are the first real
   subscribers `apps.core.events.bus` has: rather than have
   `apps.leads` or `apps.accounts` know this app exists and call it
   directly, this module listens for facts they already publish. That is
   the whole reason the bus exists — two domains stay uncoupled.

Recording an event here never raises into its caller. A quote request
succeeding must never fail because a funnel count could not be written —
the business operation is what matters; the metric is secondary and is
logged, not allowed to roll anything back.
"""

from __future__ import annotations

import logging

from apps.core.events import DomainEvent, subscribe
from apps.tracking import events
from apps.tracking.models import AgencyWebsiteEvent

logger = logging.getLogger(__name__)


def record_event(*, event_name: str, path: str = "", referrer: str = "",
                 utm_source: str = "", utm_medium: str = "",
                 utm_campaign: str = "", session_fingerprint: str = "",
                 context: str = "") -> AgencyWebsiteEvent | None:
    """Write one funnel event. Returns `None` rather than raising.

    `event_name` is checked against the closed taxonomy — an unknown name
    is logged and dropped, which is what keeps `events.FUNNEL_ORDER` a
    trustworthy, exhaustive list of what this platform actually measures.
    """
    if event_name not in events.ALL_EVENTS:
        logger.warning("Dropped an agency website event with an unknown "
                       "name: %r", event_name)
        return None

    try:
        from apps.core.operations import current

        if not current().analytics_enabled:
            return None
        return AgencyWebsiteEvent.objects.create(
            event_name=event_name, path=path[:500], referrer=referrer[:500],
            utm_source=utm_source[:100], utm_medium=utm_medium[:100],
            utm_campaign=utm_campaign[:150],
            session_fingerprint=session_fingerprint[:64],
            context=context[:200],
        )
    except Exception:  # noqa: BLE001 - a metric must never break its caller
        logger.exception("Could not record agency website event %r",
                         event_name)
        return None


# ---------------------------------------------------------------------------
# Bus subscribers — imported (and so registered) from TrackingConfig.ready()
# ---------------------------------------------------------------------------


@subscribe("lead.submission_received")
def _on_submission_received(event: DomainEvent) -> None:
    """A contact enquiry or quote request was actually stored.

    Recorded from here rather than from the public form view, so the
    funnel count can never drift from the real row count in
    `apps.leads.ContactSubmission` — the two are, by construction, the
    same event.
    """
    kind = event.payload.get("kind")
    event_name = {
        "contact": events.CONTACT_SUBMIT,
        "quote_request": events.QUOTE_SUBMIT,
    }.get(kind)
    if event_name:
        record_event(event_name=event_name)


@subscribe("account.registered")
def _on_account_registered(event: DomainEvent) -> None:
    """A new client account was created.

    `apps.accounts.services.register_client` is the only publisher of
    this event, so — unlike a generic "a user was saved" signal — this
    can only ever mean a client registration, never a staff account
    being created in the admin.
    """
    record_event(event_name=events.CLIENT_REGISTER)
