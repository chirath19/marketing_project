"""The agency website event taxonomy.

One fixed vocabulary, used everywhere an event is fired — the client-side
snippet (`static/js/tracking.js`), the server-side recorder
(`apps/tracking/services.py`), and the handful of existing domain
services this module subscribes to via the event bus. A closed list for
the same reason `apps.campaigns.registry` is one: a typo in an event name
would silently create a funnel step nobody's report ever looks at.

    page_view        — any page load, after consent.
    service_view      — the service catalogue or a category page.
    service_select     — "Add to quote" on a service detail page.
    quote_start       — the quote page first rendered with a selection in it.
    quote_submit      — a quote request was sent (apps.leads).
    contact_submit     — a contact enquiry was sent (apps.leads).
    client_register     — a new client account was created (apps.accounts).

Each one is documented here, once, so "what counts as a quote start" has
a single answer instead of five slightly different ones scattered across
views.
"""

from __future__ import annotations

PAGE_VIEW = "page_view"
SERVICE_VIEW = "service_view"
SERVICE_SELECT = "service_select"
QUOTE_START = "quote_start"
QUOTE_SUBMIT = "quote_submit"
CONTACT_SUBMIT = "contact_submit"
CLIENT_REGISTER = "client_register"

#: Every event a client (browser) may report directly, through the
#: ingestion endpoint. `quote_submit`, `contact_submit` and
#: `client_register` are **not** here — those are recorded server-side,
#: from the event bus, at the moment the thing they describe actually
#: happened in the database, which cannot be spoofed by a request to an
#: endpoint with no corresponding row.
CLIENT_REPORTABLE_EVENTS = frozenset({
    PAGE_VIEW, SERVICE_VIEW, SERVICE_SELECT, QUOTE_START,
})

#: Every event this taxonomy defines, client- or server-recorded — for
#: validating anything that claims to be one of them.
ALL_EVENTS = frozenset({
    PAGE_VIEW, SERVICE_VIEW, SERVICE_SELECT, QUOTE_START, QUOTE_SUBMIT,
    CONTACT_SUBMIT, CLIENT_REGISTER,
})

#: Display order for the funnel report — the order a visitor actually
#: moves through it, not alphabetical.
FUNNEL_ORDER = (
    PAGE_VIEW, SERVICE_VIEW, SERVICE_SELECT, QUOTE_START, QUOTE_SUBMIT,
    CONTACT_SUBMIT, CLIENT_REGISTER,
)

FUNNEL_LABELS = {
    PAGE_VIEW: "Page views",
    SERVICE_VIEW: "Service page views",
    SERVICE_SELECT: "Services selected",
    QUOTE_START: "Quotes started",
    QUOTE_SUBMIT: "Quotes submitted",
    CONTACT_SUBMIT: "Contact enquiries",
    CLIENT_REGISTER: "Client registrations",
}
