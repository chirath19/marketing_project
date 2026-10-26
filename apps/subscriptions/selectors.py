"""Read access for the Subscriptions domain.

Every queryset here is already scoped to the requesting actor and
prefetch-complete. Views, serializers and templates read through these
functions, never through a raw manager — which is how the isolation rule
stays in one place instead of being re-implemented, slightly differently,
in each view that needs it.
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.core.modules import modules_for
from apps.subscriptions import policies
from apps.subscriptions.models import (
    ClientSubscription,
    SubscriptionStatus,
)

# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


def visible_subscriptions(actor, *, status: str = "", organization=None,  # noqa: ANN001
                          search: str = "") -> QuerySet:
    """Client services this actor may see.

    Two filters, not one. `visible_to` applies the tenancy rule; the
    permission check decides whether they may see the section at all. A
    staff member with no subscriptions permission gets nothing even
    though the tenancy rule would have let them through.
    """
    if not policies.can_view_subscriptions(actor):
        return ClientSubscription.objects.none()

    queryset = ClientSubscription.objects.visible_to(actor).for_listing()

    # Assignment-scoped staff see only their own clients. Applied here
    # rather than in the view so a list and a detail page cannot disagree.
    from apps.permissions.guards import scope_to_accessible

    queryset = scope_to_accessible(queryset, actor, field="organization_id")

    if status:
        queryset = queryset.filter(status=status)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(organization__name__icontains=search)
            | Q(service__name__icontains=search)
        )

    return queryset


def get_subscription(actor, pk: int):  # noqa: ANN001, ANN201
    """One service, resolved through the same rule that filters the list.

    So a guessed id is refused by the isolation rule rather than by the
    template, and a 404 — not a 403 — is what comes back: confirming
    that another client's service exists is itself information.
    """
    return (
        visible_subscriptions(actor)
        .prefetch_related("events__actor")
        .filter(pk=pk)
        .first()
    )


def status_counts(actor) -> dict:  # noqa: ANN001
    """One row per status, for the filter bar. A single grouped query."""
    if not policies.can_view_subscriptions(actor):
        return {}

    counts = dict(
        visible_subscriptions(actor).values_list("status")
        .annotate(total=Count("pk")).values_list("status", "total")
    )
    return {status: counts.get(status, 0) for status in SubscriptionStatus.values}


def active_subscription_count(actor) -> int:  # noqa: ANN001
    """For the staff dashboard tile."""
    if not policies.can_view_subscriptions(actor):
        return 0
    return visible_subscriptions(actor).delivering().count()


def expiring_soon(actor, *, within_days: int = 30) -> QuerySet:  # noqa: ANN001
    """Live services whose agreed end date is close.

    Worth surfacing: an end date that passes unnoticed is either work
    that stops without anyone telling the client, or work that continues
    without anyone billing for it.
    """
    from datetime import timedelta

    from django.utils import timezone

    if not policies.can_view_subscriptions(actor):
        return ClientSubscription.objects.none()

    today = timezone.localdate()
    return (
        visible_subscriptions(actor)
        .filter(status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED],
                ends_on__gte=today, ends_on__lte=today + timedelta(days=within_days))
        .order_by("ends_on")
    )


def for_organization(actor, organization) -> QuerySet:  # noqa: ANN001
    """Everything sold to one client, for their staff-side profile page."""
    return visible_subscriptions(actor, organization=organization)


# ---------------------------------------------------------------------------
# What a client sees
# ---------------------------------------------------------------------------


def subscriptions_for_client(user) -> QuerySet:  # noqa: ANN001
    """This client's own services.

    Scoped by `visible_to` from the tenancy base — the single
    implementation of the rule. Nothing is filtered by hand here.
    """
    return (
        ClientSubscription.objects.visible_to(user)
        .for_listing()
        .order_by("status", "-created_at")
    )


def client_subscription(user, pk: int):  # noqa: ANN001, ANN201
    """One service a client is entitled to open, or None."""
    subscription = (
        ClientSubscription.objects
        .select_related("organization", "service", "service__category", "package")
        .prefetch_related("events__actor")
        .filter(pk=pk)
        .first()
    )
    if subscription is None or not policies.can_client_see_subscription(
        user, subscription
    ):
        return None
    return subscription


def client_visible_events(subscription) -> list:  # noqa: ANN001
    """History entries a client may read.

    Filtered here rather than in the template, because a condition
    forgotten in one template is how an internal note reaches a client.
    """
    return [event for event in subscription.events.all() if not event.is_internal]


def unlocked_modules(user) -> list:  # noqa: ANN001
    """The workspace areas this client has earned.

    **This is the answer to "do not build a dashboard per client".**
    There is one workspace; which parts of it a client can open is a
    function of their active services and nothing else.

    Only delivering services count. A paused retainer should not keep a
    live performance area open, and a cancelled one certainly should not.
    """
    keys = (
        ClientSubscription.objects.visible_to(user).delivering()
        .exclude(service__category__workspace_module="")
        .values_list("service__category__workspace_module", flat=True)
    )
    return modules_for(set(keys))
