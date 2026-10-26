"""The consent-gated event ingestion endpoint.

One POST endpoint, called by `static/js/tracking.js` after a visitor has
consented to analytics tracking. It accepts exactly the events a browser
is allowed to report — see `events.CLIENT_REPORTABLE_EVENTS` — and
rejects anything else outright, which is what stops a script from
inflating `quote_submit` or `client_register` counts that are only ever
written server-side from a real database row.

Rate-limited the same way the public contact form is: by hashed IP, a
generous ceiling, because the failure mode of being too strict is losing
real funnel data, and the failure mode of being too generous is a few
extra rows in a table nothing financial depends on.
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.ratelimit import RateLimit, check, client_ip
from apps.tracking import events
from apps.tracking.models import fingerprint_session
from apps.tracking.services import record_event

EVENT_IP_LIMIT = RateLimit("tracking:event:ip", limit=120, window=timedelta(hours=1))

#: First-party, httponly, no personal data in the value — just enough to
#: tell repeat requests in one browsing session apart from a fresh one.
#: Not used for anything except `AgencyWebsiteEvent.session_fingerprint`.
SESSION_COOKIE_NAME = "hg_sid"


def _session_id(request: HttpRequest) -> str:
    return request.COOKIES.get(SESSION_COOKIE_NAME) or secrets.token_urlsafe(16)


@csrf_exempt
@require_POST
def record(request: HttpRequest) -> JsonResponse:
    """Record one client-reportable event.

    `@csrf_exempt` because this is called before a page has necessarily
    rendered a CSRF token in some flows (e.g. the very first page view)
    and it writes nothing sensitive — the rate limit and the closed
    event taxonomy are the actual defence, not a CSRF token a metrics
    beacon has no reason to carry.
    """
    verdict = check(EVENT_IP_LIMIT, client_ip(request))
    if not verdict.allowed:
        return JsonResponse({"ok": False}, status=429)

    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"ok": False}, status=400)

    event_name = str(payload.get("event", ""))[:40]
    if event_name not in events.CLIENT_REPORTABLE_EVENTS:
        # Not an error worth a 4xx: an old cached page running an older
        # script version should not generate noise in the logs.
        return JsonResponse({"ok": True})

    session_id = _session_id(request)

    record_event(
        event_name=event_name,
        path=str(payload.get("path", ""))[:500],
        referrer=str(payload.get("referrer", ""))[:500],
        utm_source=str(payload.get("utm_source", ""))[:100],
        utm_medium=str(payload.get("utm_medium", ""))[:100],
        utm_campaign=str(payload.get("utm_campaign", ""))[:150],
        session_fingerprint=fingerprint_session(session_id),
        context=str(payload.get("context", ""))[:200],
    )

    response = JsonResponse({"ok": True})
    if SESSION_COOKIE_NAME not in request.COOKIES:
        # 30 minutes: long enough to cover one browsing session, short
        # enough that it is gone well before anyone could call it a
        # persistent identifier.
        response.set_cookie(
            SESSION_COOKIE_NAME, session_id, max_age=30 * 60,
            httponly=True, samesite="Lax",
        )
    return response
