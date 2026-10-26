"""Read access for the agency website analytics domain.

Two kinds of number live on the Agency Website analytics page, and they
come from two different places on purpose:

* **Funnel counts** (`funnel_for`) — real, first-party, counted from
  `AgencyWebsiteEvent`. Always available, because recording them needs
  no external configuration.
* **GA4 site totals** (`ga4_summary_for`) — visitors, sessions, page
  views as GA4 itself measures them. These depend on a configured GA4
  reporting connection (`apps.integrations`) and are `None` until one
  exists — the admin page is the thing that turns `None` into "Website
  analytics integration has not been configured," never into a zero.
"""

from __future__ import annotations

from apps.analytics.dateranges import DateRange
from apps.tracking import events
from apps.tracking.models import AgencyWebsiteEvent


def funnel_for(date_range: DateRange) -> list[dict]:
    """Event counts for the funnel, in the order a visitor moves through it.

    One query, grouped, rather than one `count()` per event name — the
    difference between one round trip and seven as this page grows.
    """
    from django.db.models import Count

    counts = dict(
        AgencyWebsiteEvent.objects.between(date_range.start, date_range.end)
        .values_list("event_name")
        .annotate(total=Count("pk"))
        .values_list("event_name", "total")
    )

    return [
        {"key": name, "label": events.FUNNEL_LABELS[name],
         "value": counts.get(name, 0)}
        for name in events.FUNNEL_ORDER
    ]


def funnel_delta(current: DateRange) -> list[dict]:
    """The funnel for `current`, each row carrying its change vs the
    equivalent previous period — section 36's "vs previous period"."""
    now_counts = {row["key"]: row["value"] for row in funnel_for(current)}
    previous_counts = {row["key"]: row["value"]
                       for row in funnel_for(current.previous)}

    rows = []
    for name in events.FUNNEL_ORDER:
        now = now_counts.get(name, 0)
        before = previous_counts.get(name, 0)
        rows.append({
            "key": name, "label": events.FUNNEL_LABELS[name], "value": now,
            # `None` rather than a percentage when there is nothing to
            # compare against — a jump from 0 to 3 is not "infinite
            # percent", it is simply not comparable yet.
            "delta_percent": (
                round((now - before) / before * 100) if before else None
            ),
        })
    return rows


def traffic_sources_for(date_range: DateRange) -> list[dict]:
    """UTM source breakdown from recorded page views.

    First-party and real, unlike the richer "Traffic Sources" GA4 itself
    would report (which also sees referrer-detected channels GA4 derives
    without a UTM tag). This is deliberately the honest subset: only
    what this platform can actually attribute from a tagged link.
    """
    from django.db.models import Count

    rows = (
        AgencyWebsiteEvent.objects.between(date_range.start, date_range.end)
        .named(events.PAGE_VIEW)
        .exclude(utm_source="")
        .values("utm_source")
        .annotate(total=Count("pk"))
        .order_by("-total")[:10]
    )
    return [{"source": row["utm_source"], "value": row["total"]} for row in rows]


def top_pages_for(date_range: DateRange) -> list[dict]:
    from django.db.models import Count

    rows = (
        AgencyWebsiteEvent.objects.between(date_range.start, date_range.end)
        .named(events.PAGE_VIEW)
        .exclude(path="")
        .values("path")
        .annotate(total=Count("pk"))
        .order_by("-total")[:10]
    )
    return [{"path": row["path"], "value": row["total"]} for row in rows]


def ga4_summary_for(date_range: DateRange) -> dict | None:
    """Visitors, sessions and page views, as GA4 itself measures them.

    `None` when no GA4 reporting connection exists — see the module
    docstring. This function is the single place that distinction is
    made, so a template never has to guess whether a missing number
    means "zero" or "not connected."
    """
    from apps.integrations.models import Provider
    from apps.integrations.selectors import connection_for

    connection = connection_for(organization=None, provider=Provider.GOOGLE_ANALYTICS)
    if connection is None or not connection.is_configured:
        return None

    from apps.integrations.providers import get_adapter
    from apps.integrations.providers.base import ProviderNotConfigured

    adapter = get_adapter(Provider.GOOGLE_ANALYTICS)
    try:
        data = adapter.fetch_site_metrics(connection, start=date_range.start,
                                          end=date_range.end)
    except ProviderNotConfigured:
        return None
    return data or None
