"""A client's own campaigns, inside their portal.

Two surfaces, one query. `/organization/area/campaigns/` shows everything
across every service; a service area's own page shows the same campaigns
filtered to its type. Both call `campaigns_for_client`, so they can never
disagree about what a client has.

A client holds no platform permission, so there is none to require. Every
view resolves the record through `selectors.client_campaign`, which
applies the tenancy rule to the row itself, and the pages themselves are
reached only through the portal's entitlement guard.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.analytics.forms import CampaignDateRangeForm
from apps.campaigns import selectors
from apps.campaigns.models import CLOSED_STATUSES, RUNNING_STATUSES


@login_required
def campaign_detail(request: HttpRequest, pk: int) -> HttpResponse:
    campaign = selectors.client_campaign(request.user, pk)
    if campaign is None:
        # 404, not 403. Confirming another client's campaign exists is
        # itself information they should not get.
        raise Http404("No such campaign.")

    date_form = CampaignDateRangeForm(request.GET)
    date_form.is_valid()
    date_range = date_form.resolve_for(campaign)

    return render(request, "campaigns/client/detail.html", {
        "page_title": campaign.name,
        "portal_key": "campaigns",
        "campaign": campaign,
        # Filtered in the selector, not here: a condition forgotten in
        # one template is how an internal note reaches a client.
        "events": selectors.client_visible_events(campaign),
        "date_form": date_form,
        "date_range": date_range,
        "performance": performance_for(request.user, campaign, date_range),
        "platform_label": _platform_label(campaign),
    })


def _platform_label(campaign) -> str:
    """The platform badge text for a paid promotion, e.g. "Meta" —
    section 4's field the generic `Campaign` deliberately does not
    carry. Blank for every other service type, which has no platform
    in the advertising sense."""
    if campaign.service_type != "paid_ads":
        return ""
    detail = campaign.detail
    return detail.get_platform_display() if detail is not None else ""


def performance_for(user, campaign, date_range) -> dict | None:
    """The one real-numbers block this campaign's type can show, or
    `None` when there is nowhere to get one from yet.

    Only Paid Ads has synced or manually-recorded daily metrics today —
    see `apps/integrations/services.py::_store_for_campaign`'s own
    docstring. A campaign type with no performance source is not an
    error; the template shows an honest "not available for this
    service yet" rather than guessing.
    """
    if campaign.service_type != "paid_ads":
        return None

    from apps.paid_ads import policies as paid_ads_policies
    from apps.paid_ads import selectors as paid_ads_selectors

    if not paid_ads_policies.can_read(user, campaign.organization):
        return None

    filters = {
        "start": date_range.start, "end": date_range.end,
        "currency": campaign.currency.upper(), "platform": "",
        "campaign": campaign,
    }
    return paid_ads_selectors.report(user, campaign.organization, filters)


def grouped_for_client(user, *, service_type: str = "") -> dict:  # noqa: ANN001
    """Campaigns split into the three groups a client reads them in.

    A plain function rather than a view, because two pages need it: the
    combined campaigns area and each service area's own. Keeping it here
    means neither has to know how the grouping works.
    """
    campaigns = list(
        selectors.campaigns_for_client(user, service_type=service_type)
    )
    return {
        "running": [c for c in campaigns if c.status in RUNNING_STATUSES],
        "upcoming": [c for c in campaigns
                     if c.is_open and c.status not in RUNNING_STATUSES],
        "finished": [c for c in campaigns if c.status in CLOSED_STATUSES],
        "total": len(campaigns),
    }
