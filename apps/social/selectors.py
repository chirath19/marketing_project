"""Organization and visibility scoped reads shared by the staff and client workspaces."""

from django.db.models import Sum

from apps.campaigns.models import Campaign
from apps.social import policies
from apps.social.models import (
    METRICS,
    ContentItem,
    CreatorPartnership,
    SocialApproval,
    SocialChannel,
    SocialDeliverable,
    SocialMetric,
)


def _scope(model, actor, organization):
    if not policies.can_read(actor, organization):
        return model.objects.none()
    return model.objects.filter(organization=organization)


def campaigns_for(actor, organization):
    return _scope(Campaign, actor, organization).filter(service_type="social").order_by("name")


def channels_for(actor, organization):
    return _scope(SocialChannel, actor, organization)


def partnerships_for(actor, organization):
    rows = _scope(CreatorPartnership, actor, organization).select_related("campaign")
    return rows if actor.is_staff_member else rows.filter(client_visible=True)


def content_for(actor, organization):
    rows = _scope(ContentItem, actor, organization).select_related(
        "campaign", "channel", "partnership"
    )
    return rows if actor.is_staff_member else rows.filter(client_visible=True)


def deliverables_for(actor, organization):
    rows = (
        _scope(SocialDeliverable, actor, organization)
        .select_related("content")
        .prefetch_related("approvals__decided_by")
    )
    return (
        rows
        if actor.is_staff_member
        else rows.filter(client_visible=True, content__client_visible=True)
    )


def reviews_for(actor, organization):
    return (
        _scope(SocialApproval, actor, organization)
        .filter(deliverable__in=deliverables_for(actor, organization))
        .select_related("deliverable__content", "decided_by")
    )


def metrics_for(actor, organization):
    return (
        _scope(SocialMetric, actor, organization)
        .filter(content__in=content_for(actor, organization))
        .select_related("content__channel")
    )


def workspace(actor, organization, filters):
    content = content_for(actor, organization)
    for field in ("campaign", "channel", "status", "kind"):
        if filters.get(field):
            content = content.filter(**{field: filters[field]})
    # Schedule filters apply to work; result dates apply to observations independently.
    scheduled = content
    if filters.get("start"):
        scheduled = scheduled.filter(scheduled_at__date__gte=filters["start"])
    if filters.get("end"):
        scheduled = scheduled.filter(scheduled_at__date__lte=filters["end"])
    results = metrics_for(actor, organization).filter(content__in=content)
    if filters.get("start"):
        results = results.filter(date__gte=filters["start"])
    if filters.get("end"):
        results = results.filter(date__lte=filters["end"])
    totals = results.aggregate(**{field: Sum(field) for field in METRICS})
    reviews = reviews_for(actor, organization).filter(
        status="pending", deliverable__content__in=scheduled
    )
    return {
        "content_items": scheduled,
        "results": results,
        "totals": totals,
        "content_count": scheduled.count(),
        "pending_reviews": reviews.count(),
    }


def delivery_cards(actor, organization, content):
    cards = []
    for delivery in deliverables_for(actor, organization).filter(content=content):
        reviews = list(delivery.approvals.all())
        current = next(
            (
                review
                for review in reviews
                if review.deliverable_revision == delivery.revision
                and review.content_revision == content.revision
                and review.status != "cancelled"
            ),
            None,
        )
        cards.append({"delivery": delivery, "reviews": reviews, "current": current})
    return cards
