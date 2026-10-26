"""Scoped manual reports and explicitly shared client deliverables."""

from django.db.models import Sum

from apps.campaigns.models import Campaign
from apps.email_marketing import policies
from apps.email_marketing.models import (
    METRICS,
    EmailApproval,
    EmailDeliverable,
    EmailMetric,
    EmailWorkItem,
)


def _scope(model, actor, organization):
    if not policies.can_read(actor, organization):
        return model.objects.none()
    return model.objects.filter(organization=organization)


def campaigns_for(actor, organization):
    return (
        _scope(Campaign, actor, organization)
        .filter(service_type="email_marketing")
        .order_by("name")
    )


def work_for(actor, organization):
    rows = _scope(EmailWorkItem, actor, organization).select_related("campaign")
    return rows if getattr(actor, "is_staff_member", False) else rows.filter(client_visible=True)


def deliverables_for(actor, organization):
    rows = (
        _scope(EmailDeliverable, actor, organization)
        .select_related("work")
        .prefetch_related("approvals__decided_by")
    )
    return (
        rows
        if getattr(actor, "is_staff_member", False)
        else rows.filter(client_visible=True, work__client_visible=True)
    )


def reviews_for(actor, organization):
    return (
        _scope(EmailApproval, actor, organization)
        .filter(deliverable__in=deliverables_for(actor, organization))
        .select_related("deliverable__work", "decided_by")
    )


def metrics_for(actor, organization):
    return (
        _scope(EmailMetric, actor, organization)
        .filter(work__in=work_for(actor, organization))
        .select_related("work")
    )


def workspace(actor, organization, filters):
    work = work_for(actor, organization)
    for field in ("campaign", "kind", "status"):
        if filters.get(field):
            work = work.filter(**{field: filters[field]})
    scheduled = work
    results = metrics_for(actor, organization).filter(work__in=work)
    if filters.get("start"):
        scheduled = scheduled.filter(scheduled_at__date__gte=filters["start"])
        results = results.filter(date__gte=filters["start"])
    if filters.get("end"):
        scheduled = scheduled.filter(scheduled_at__date__lte=filters["end"])
        results = results.filter(date__lte=filters["end"])
    return {
        "work_items": scheduled,
        "results": results,
        "work_count": scheduled.count(),
        "pending_reviews": reviews_for(actor, organization)
        .filter(status="pending", deliverable__work__in=scheduled)
        .count(),
        "totals": results.aggregate(**{field: Sum(field) for field in METRICS}),
    }


def delivery_cards(actor, organization, work):
    cards = []
    for delivery in deliverables_for(actor, organization).filter(work=work):
        reviews = list(delivery.approvals.all())
        current = next(
            (
                review
                for review in reviews
                if review.deliverable_revision == delivery.revision
                and review.work_revision == work.revision
                and review.status != "cancelled"
            ),
            None,
        )
        cards.append({"delivery": delivery, "reviews": reviews, "current": current})
    return cards
