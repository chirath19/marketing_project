"""Organization-scoped reporting; ratios are calculated from summed observations."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum

from apps.paid_ads import policies
from apps.paid_ads.models import (
    DEFAULT_PRIORITY,
    MEASURES,
    DailyAdMetric,
    PaidAdsCampaignDetail,
    PaidAdsGoal,
    Platform,
    priority_for,
)

#: Client-friendly labels for every measure and ratio this report can
#: show — section 45's instruction not to make a business owner decode
#: a provider's own metric name.
METRIC_LABELS = {
    "spend": "Ad spend", "impressions": "Impressions", "clicks": "Clicks",
    "leads": "Leads", "conversions": "Conversions", "revenue": "Revenue",
    "reach": "Reach", "link_clicks": "Link clicks",
    "landing_page_views": "Landing page views", "engagements": "Engagements",
    "video_views": "Video views",
    "roas": "ROAS", "cpl": "CPL", "cpa": "CPA", "ctr": "CTR", "cpc": "CPC",
    "cpm": "CPM", "frequency": "Frequency", "engagement_rate": "Engagement rate",
    "cost_per_engagement": "Cost per engagement",
    "cost_per_video_view": "Cost per video view",
    "cost_per_link_click": "Cost per link click",
}

#: One plain sentence per technical metric, for a tooltip — only the
#: ones a business owner would not already know from the label.
METRIC_HELP = {
    "ctr": "Percentage of impressions that resulted in a click.",
    "cpc": "Average advertising cost for each click.",
    "cpm": "Average advertising cost for every 1,000 impressions.",
    "cpl": "Average advertising cost for each lead generated.",
    "cpa": "Average advertising cost for each conversion.",
    "roas": "Revenue attributed to advertising divided by ad spend.",
    "frequency": "Average number of times one person saw this campaign.",
    "engagement_rate": "Engagements as a percentage of the people reached.",
    "cost_per_engagement": "Average advertising cost for each engagement.",
    "cost_per_video_view": "Average advertising cost for each video view.",
}


def campaigns_for(actor, organization):
    from apps.campaigns.models import Campaign

    if not policies.can_read(actor, organization):
        return Campaign.objects.none()
    return Campaign.objects.filter(organization=organization, service_type="paid_ads").order_by(
        "name"
    )


def metrics_for(actor, organization):
    if not policies.can_read(actor, organization):
        return DailyAdMetric.objects.none()
    return DailyAdMetric.objects.filter(organization=organization).select_related("campaign")


def goals_for(actor, organization):
    if not policies.can_read(actor, organization):
        return PaidAdsGoal.objects.none()
    return PaidAdsGoal.objects.filter(organization=organization).select_related("campaign")


def _sums():
    return {name: Sum(name, default=0) for name in MEASURES}


#: Every ratio this report can calculate, and the two sums it divides.
#: `cpm` and the cost-per-X ratios are weighted period totals, the same
#: way `ctr` always has been — not an average of daily ratios, which
#: would weight a quiet day the same as a busy one.
RATIOS: tuple[tuple[str, str, str, int], ...] = (
    ("roas", "revenue", "spend", 1),
    ("cpl", "spend", "leads", 1),
    ("cpa", "spend", "conversions", 1),
    ("ctr", "clicks", "impressions", 100),
    ("cpc", "spend", "clicks", 1),
    ("cpm", "spend", "impressions", 1000),
    ("frequency", "impressions", "reach", 1),
    ("engagement_rate", "engagements", "reach", 100),
    ("cost_per_engagement", "spend", "engagements", 1),
    ("cost_per_video_view", "spend", "video_views", 1),
    ("cost_per_link_click", "spend", "link_clicks", 1),
)

MONEY_RATIOS = frozenset({"cpl", "cpc", "cpm", "cpa", "cost_per_engagement",
                          "cost_per_video_view", "cost_per_link_click"})
PERCENT_RATIOS = frozenset({"ctr", "engagement_rate"})


def calculated(totals):
    """Weighted period ratios. Zero denominators and absent observations are unavailable."""
    values = dict(totals)
    for key, numerator, denominator, multiplier in RATIOS:
        denominator_value = values.get(denominator) or 0
        values[key] = (
            Decimal(values[numerator] or 0) / Decimal(denominator_value) * multiplier
            if denominator_value
            else None
        )
    return values


def display_value(metric, value, currency):
    if value is None:
        return "—"
    if metric in {"spend", "revenue", *MONEY_RATIOS}:
        return f"{currency} {value:,.2f}"
    if metric == "roas":
        return f"{value:,.2f}×"
    if metric in PERCENT_RATIOS:
        return f"{value:,.2f}%"
    if metric == "frequency":
        return f"{value:,.2f}"
    return f"{value:,.0f}"


def _decorate(values, currency):
    values = calculated(values)
    values["display"] = {
        key: display_value(key, values[key], currency)
        for key in (*MEASURES, *(ratio[0] for ratio in RATIOS))
    }
    return values


def _goal_progress(actor, organization, filters):
    goals = goals_for(actor, organization).filter(
        is_active=True,
        currency=filters["currency"],
        starts_on__lte=filters["end"],
        ends_on__gte=filters["start"],
    )
    if filters.get("platform"):
        goals = goals.filter(platform=filters["platform"])
    if filters.get("campaign"):
        goals = goals.filter(campaign=filters["campaign"])
    goals = list(goals)
    if not goals:
        return []
    # One observation query for all goal windows, avoiding a query per goal.
    records = list(
        metrics_for(actor, organization)
        .filter(
            currency=filters["currency"],
            date__gte=min(g.starts_on for g in goals),
            date__lte=max(g.ends_on for g in goals),
        )
        .values("date", "platform", "campaign_id", *MEASURES)
    )
    results = []
    for goal in goals:
        matching = [
            r
            for r in records
            if goal.starts_on <= r["date"] <= goal.ends_on
            and (not goal.platform or r["platform"] == goal.platform)
            and (not goal.campaign_id or r["campaign_id"] == goal.campaign_id)
        ]
        current = None
        if matching:
            totals = {name: sum((r[name] or 0) for r in matching) for name in MEASURES}
            current = calculated(totals)[goal.metric]
        met = (
            None
            if current is None
            else (current <= goal.target if goal.is_ceiling else current >= goal.target)
        )
        results.append(
            {
                "goal": goal,
                "current": display_value(goal.metric, current, goal.currency),
                "target": display_value(goal.metric, goal.target, goal.currency),
                "assessment": (
                    "No data"
                    if met is None
                    else "Within ceiling so far"
                    if met and goal.is_ceiling
                    else "Target reached"
                    if met
                    else "Above ceiling"
                    if goal.is_ceiling
                    else "Below target"
                ),
            }
        )
    return results


def report(actor, organization, filters):
    if not policies.can_read(actor, organization):
        raise PermissionDenied("This advertising workspace is not available to you.")
    rows = metrics_for(actor, organization).filter(
        date__gte=filters["start"],
        date__lte=filters["end"],
        currency=filters["currency"],
    )
    if filters.get("platform"):
        rows = rows.filter(platform=filters["platform"])
    if filters.get("campaign"):
        rows = rows.filter(campaign=filters["campaign"])
    totals = rows.aggregate(records=Count("pk"), **_sums())
    currency = filters["currency"]
    totals = _decorate(totals, currency)
    platforms = []
    for row in rows.order_by().values("platform").annotate(**_sums()).order_by("platform"):
        platforms.append({**_decorate(row, currency), "label": Platform(row["platform"]).label})
    campaigns = [
        {
            **_decorate(row, currency),
            "label": row["campaign__name"],
            "status": row["campaign__status"],
        }
        for row in rows.order_by()
        .values("campaign_id", "campaign__name", "campaign__status")
        .annotate(**_sums())
        .order_by("campaign__name")
    ]
    daily = [
        {**_decorate(row, currency), "label": row["date"]}
        for row in rows.order_by().values("date").annotate(**_sums()).order_by("date")
    ]

    # One campaign, selected: lead with the KPIs its own objective says
    # matter (section 10) rather than a one-size-fits-all list. Several
    # campaigns, or none chosen: a sensible general-purpose order.
    single_campaign = filters.get("campaign")
    kpi_keys = DEFAULT_PRIORITY
    if single_campaign is not None:
        detail = PaidAdsCampaignDetail.objects.filter(campaign=single_campaign).first()
        if detail is not None:
            kpi_keys = priority_for(detail.objective)

    previous = None
    span = (filters["end"] - filters["start"]).days + 1
    previous_start = filters["start"] - timedelta(days=span)
    previous_end = filters["start"] - timedelta(days=1)
    previous_rows = metrics_for(actor, organization).filter(
        date__gte=previous_start, date__lte=previous_end,
        currency=filters["currency"],
    )
    if filters.get("platform"):
        previous_rows = previous_rows.filter(platform=filters["platform"])
    if single_campaign:
        previous_rows = previous_rows.filter(campaign=single_campaign)
    previous_totals_raw = previous_rows.aggregate(records=Count("pk"), **_sums())
    if previous_totals_raw["records"]:
        previous = _decorate(previous_totals_raw, currency)

    campaign_list = campaigns_for(actor, organization)
    if single_campaign:
        campaign_list = campaign_list.filter(pk=single_campaign.pk)
    return {
        "has_data": bool(totals["records"]),
        "totals": totals,
        "kpis": _kpi_rows(totals, previous, kpi_keys),
        "platform_rows": platforms,
        "campaign_rows": campaigns,
        "daily_rows": daily,
        "records": rows,
        "goals": _goal_progress(actor, organization, filters),
        "campaigns": campaign_list,
        "currency": currency,
        "previous_totals": previous,
        "provider_connected": _has_ad_connection(organization),
    }


def _has_ad_connection(organization) -> bool:
    """Whether any advertising provider is actually connected for this
    client — decides the banner wording between "entered by staff" and
    "includes synced results" (section 55: never blur the two)."""
    from apps.integrations.models import ConnectionStatus, IntegrationConnection, Provider

    ad_providers = (Provider.META_ADS, Provider.GOOGLE_ADS,
                    Provider.LINKEDIN_ADS, Provider.TIKTOK_ADS)
    return IntegrationConnection.objects.filter(
        organization=organization, provider__in=ad_providers,
        status=ConnectionStatus.CONNECTED,
    ).exists()


#: Metrics where a smaller number is the improvement — every cost-per-X
#: ratio. Everything else (spend aside, which is a budget fact rather
#: than a result) is read the usual way: more is better.
LOWER_IS_BETTER = MONEY_RATIOS


def _kpi_rows(totals, previous, keys):
    """One row per KPI, with a period-over-period delta where a
    comparable previous period actually has data (section 19 — never
    calculated against zero or missing history)."""
    rows = []
    for key in keys:
        value = totals["display"].get(key)
        delta_percent = None
        direction = "neutral"
        if previous is not None:
            current = totals.get(key)
            before = previous.get(key)
            if current is not None and before:
                delta_percent = round((current - before) / before * 100)
                if delta_percent != 0:
                    rose = delta_percent > 0
                    improved = (not rose) if key in LOWER_IS_BETTER else rose
                    direction = "good" if improved else "bad"
        rows.append({
            "key": key, "label": METRIC_LABELS.get(key, key),
            "help": METRIC_HELP.get(key, ""), "value": value,
            "delta_percent": delta_percent,
            "delta_text": (f"{delta_percent:+d}% vs previous period"
                          if delta_percent is not None else ""),
            "direction": direction,
        })
    return rows
