"""Read access for the Campaigns domain.

Every queryset here is already scoped to the requesting actor and
prefetch-complete. Views, serializers and templates read through these,
never through a raw manager — which is how the isolation rule stays in
one place instead of being re-implemented, slightly differently, in each
view that needs it.

`of_type` is the hook service modules use. A future SEO dashboard calls
`visible_campaigns(actor, service_type="seo")` rather than querying a
table of its own.
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.campaigns import policies
from apps.campaigns.models import Campaign, CampaignStatus

# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


def visible_campaigns(actor, *, status: str = "", service_type: str = "",  # noqa: ANN001
                      organization=None, owner: str = "",
                      search: str = "") -> QuerySet:
    """Campaigns this actor may see.

    Two filters, not one. `visible_to` applies the tenancy rule; the
    permission check decides whether they may see the section at all; and
    `scope_to_accessible` narrows staff to the clients they are assigned
    to. A list that skipped the last would be a quiet way around every
    object-level check.
    """
    if not policies.can_view_campaigns(actor):
        return Campaign.objects.none()

    from apps.permissions.guards import scope_to_accessible

    queryset = scope_to_accessible(
        Campaign.objects.visible_to(actor).for_listing(),
        actor, field="organization_id",
    )
    queryset = _enabled_areas(queryset, actor)

    if status:
        queryset = queryset.filter(status=status)
    if service_type:
        queryset = queryset.of_type(service_type)
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    if owner == "me":
        queryset = queryset.filter(Q(owner=actor) | Q(assignees=actor)).distinct()
    elif owner == "none":
        queryset = queryset.filter(owner__isnull=True)

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(objective__icontains=search)
            | Q(description__icontains=search)
            | Q(organization__name__icontains=search)
        )

    return queryset


def get_campaign(actor, pk: int):  # noqa: ANN001, ANN201
    """One campaign, through the same rule that filters the list.

    So a guessed id is refused by the isolation rule rather than by the
    template, and a 404 — not a 403 — comes back: confirming that another
    client's campaign exists is itself information.
    """
    return (
        visible_campaigns(actor)
        .prefetch_related("events__actor")
        .filter(pk=pk)
        .first()
    )


def status_counts(actor, **filters) -> dict:  # noqa: ANN001
    """One row per status, for the filter bar. A single grouped query."""
    if not policies.can_view_campaigns(actor):
        return {}

    counts = dict(
        visible_campaigns(actor, **filters).values_list("status")
        .annotate(total=Count("pk", distinct=True))
        .values_list("status", "total")
    )
    return {status: counts.get(status, 0) for status in CampaignStatus.values}


def type_counts(actor) -> dict:  # noqa: ANN001
    """How many campaigns sit in each service area."""
    if not policies.can_view_campaigns(actor):
        return {}

    return dict(
        visible_campaigns(actor).values_list("service_type")
        .annotate(total=Count("pk", distinct=True))
        .values_list("service_type", "total")
    )


def running_count(actor) -> int:  # noqa: ANN001
    """For the staff dashboard tile."""
    if not policies.can_view_campaigns(actor):
        return 0
    return visible_campaigns(actor).running().count()


def overdue(actor) -> QuerySet:  # noqa: ANN001
    """Open campaigns whose end date has passed.

    Worth surfacing: an end date that goes by unnoticed is either work
    stopping without anyone saying so, or work continuing past what was
    agreed.
    """
    if not policies.can_view_campaigns(actor):
        return Campaign.objects.none()
    return visible_campaigns(actor).overdue().order_by("ends_on")


def for_organization(actor, organization) -> QuerySet:  # noqa: ANN001
    """Everything running for one client, for their staff profile page."""
    return visible_campaigns(actor, organization=organization)


def for_subscription(actor, subscription) -> QuerySet:  # noqa: ANN001
    """Campaigns delivered under one service."""
    if not policies.can_view_campaigns(actor):
        return Campaign.objects.none()
    return visible_campaigns(actor).filter(subscription=subscription)


# ---------------------------------------------------------------------------
# What a client sees
# ---------------------------------------------------------------------------


def campaigns_for_client(user, *, service_type: str = "", subscription=None) -> QuerySet:  # noqa: ANN001
    """This client's own campaigns, across every service.

    Scoped by `visible_to` from the tenancy base — the single
    implementation of the rule. Nothing is filtered by hand here.

    `service_type` is what lets one query serve both the combined
    campaigns page and each service area's own page. `subscription` is
    the same idea for "My Package" (section 16): the client's own
    service detail page asks for campaigns delivered under *this*
    subscription specifically.
    """
    queryset = (
        Campaign.objects.visible_to(user)
        .for_listing()
        .order_by("status", "-starts_on", "-created_at")
    )
    queryset = _enabled_areas(queryset, user)
    if service_type:
        queryset = queryset.of_type(service_type)
    if subscription is not None:
        queryset = queryset.filter(subscription=subscription)
    return queryset


def _enabled_areas(queryset, actor):
    from apps.core.features import FEATURES, visible

    disabled = [key for key in FEATURES if not visible(key, actor)]
    return queryset.exclude(service_type__in=disabled)


def client_campaign(user, pk: int):  # noqa: ANN001, ANN201
    """One campaign a client is entitled to open, or None."""
    campaign = (
        Campaign.objects
        .select_related("organization", "subscription", "subscription__service")
        .prefetch_related("events__actor")
        .filter(pk=pk)
        .first()
    )
    if campaign is None or not policies.can_client_see_campaign(user, campaign):
        return None
    return campaign


def client_visible_events(campaign) -> list:  # noqa: ANN001
    """History entries a client may read.

    Filtered here rather than in the template, because a condition
    forgotten in one template is how an internal note reaches a client.
    """
    return [event for event in campaign.events.all() if not event.is_internal]
