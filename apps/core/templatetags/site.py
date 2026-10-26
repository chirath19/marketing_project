"""Display helpers for the public marketing site.

Kept apart from `ui.py` on purpose: that library dresses the whole
product, including the dashboards, while everything here exists only to
make a decision about how a marketing page reads. Nothing in the
signed-in workspace loads this module.
"""

from __future__ import annotations

import re

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def quote_selected(context, service, package=None) -> bool:  # noqa: ANN001
    from apps.catalog.quote_selection import selection_state

    state = selection_state(context["request"])
    if package:
        return state.get(str(service.pk)) == str(package.pk)
    return str(service.pk) in state


@register.simple_tag(takes_context=True)
def quote_count(context) -> int:  # noqa: ANN001
    """How many services are sitting in the visitor's quote.

    Shown as a badge on the header's call to action, so somebody who
    added something three pages ago can see that it is still there. Reads
    `apps.catalog.quote_selection`, the same session list the quote page
    resolves against — it never counts something the quote page would
    then drop.
    """
    request = context.get("request")
    if request is None or not hasattr(request, "session"):
        return 0
    try:
        from apps.catalog.quote_selection import SESSION_KEY

        value = request.session.get(SESSION_KEY)
        return len(value) if isinstance(value, list) else 0
    except Exception:  # noqa: BLE001 — a badge must never 500 a page
        return 0


@register.simple_tag
def service_names(limit: int = 18) -> list[str]:
    """The names of the services actually on sale, for the hero ticker.

    Reads `apps.catalog.selectors.live_services`, which is the same
    queryset the catalogue page uses — so the ticker can never advertise
    something a visitor cannot then click through and buy, and it says
    nothing the agency has not published.

    One query, and the home hero is the only caller: `hero.html` gates
    the ticker on `is_home`. The catalogue has its own, richer
    `live_services()` with prefetches, and a second one for a decorative
    strip above the same list is a cost with nothing to show for it.

    Returns an empty list rather than raising if the catalogue is not
    installed or the table is not migrated yet; the hero simply renders
    without the ticker.
    """
    try:
        from apps.catalog.selectors import live_services

        return list(live_services().values_list("name", flat=True)[:limit])
    except Exception:  # noqa: BLE001 — a marketing flourish must never 500 a page
        return []

# "1. Discovery", "2) Review", "03 — Strategy": an editor numbering a
# list by hand, in any of the ways people actually write it.
_LEADING_NUMBER = re.compile(r"^\s*\d+\s*[.)\-–—:]")


@register.filter
def is_numbered(label: object) -> bool:
    """True when the text already begins with its own number.

    The feature grid numbers its items, which is what gives a plain list
    of disciplines its editorial rhythm. When the same section is used
    for a process the editor has usually numbered the steps in the label
    too, and the grid would then print "01" above "1. Discovery". This
    lets the template stand its own numbering down rather than asking
    the editor to write the labels differently.
    """
    return bool(_LEADING_NUMBER.match(str(label or "")))


@register.simple_tag
def service_disciplines() -> list[str]:
    """Published catalogue categories for the static home-hero discipline strip."""
    from apps.catalog.selectors import live_services

    return list(
        live_services().order_by("category__order", "category__name")
        .values_list("category__name", flat=True).distinct()
    )


# The line motifs in `templates/public/_motif.html`, by what each one
# draws. A card asks for one by name rather than by number, so renaming
# or reordering the drawings cannot silently swap every mark on the
# catalogue.
MOTIFS = {
    "signal": 1,
    "trend": 2,
    "approval": 3,
    "target": 4,
    "message": 5,
    "measure": 6,
    "schedule": 7,
    "audience": 8,
}

#: Which motif stands for which catalogue category. Position in a grid
#: is a bad way to choose a picture — it put an envelope on "On-page
#: SEO" — so the discipline chooses instead, and a category reads the
#: same mark wherever its services happen to land in the grid.
CATEGORY_MOTIFS = {
    "search": "signal",
    "paid": "target",
    "social": "audience",
    "email": "message",
    "analytics": "measure",
    "strategy": "schedule",
    "content": "approval",
}


@register.filter
def motif_for(slug: object) -> int:
    """The motif number for a catalogue category.

    A category added after this mapping was written still gets a stable
    mark rather than falling through to the same default as every other
    unknown one: the slug is spread across the set, so two new
    categories are unlikely to collide and neither will change its mark
    between requests.
    """
    key = str(slug or "")
    name = CATEGORY_MOTIFS.get(key)
    if name:
        return MOTIFS[name]
    if not key:
        return MOTIFS["signal"]
    return sum(ord(character) for character in key) % len(MOTIFS) + 1


@register.simple_tag
def catalogue_totals() -> dict:
    """How many services, across how many disciplines, are on sale.

    The home hero states these as facts about the agency, so they are
    counted from the same published catalogue the services page lists
    rather than typed into a template — a number written by hand goes
    stale the first time somebody retires a service, and a marketing
    page that overstates its own catalogue is the worst kind of wrong.

    Returns zeroes rather than raising if the catalogue is not migrated
    yet; the hero drops the strip instead of failing the page.
    """
    try:
        from apps.catalog.selectors import live_services

        services = live_services()
        return {
            "services": services.count(),
            "disciplines": services.values("category_id").distinct().count(),
        }
    except Exception:  # noqa: BLE001 — a marketing flourish must never 500 a page
        return {"services": 0, "disciplines": 0}
