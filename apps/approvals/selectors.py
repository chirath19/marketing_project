"""Shared inbox and dashboard indicators, scoped before pagination and counting."""

from django.db.models import Q

from apps.approvals import policies
from apps.approvals.models import ApprovalRequest
from apps.campaigns.models import Campaign
from apps.permissions.guards import scope_to_accessible
from apps.subscriptions.guards import entitlement_keys


def requests_for(actor, organization=None):
    rows = ApprovalRequest.objects.select_related(
        "organization",
        "campaign",
        "requested_by",
        "resolved_by",
        "social_review__deliverable__content",
        "email_review__deliverable__work",
    )
    if not policies.can_open(actor, organization):
        return rows.none()
    if actor.is_staff_member:
        rows = scope_to_accessible(rows, actor)
        return rows.filter(organization=organization) if organization else rows
    keys = entitlement_keys(actor, organization=organization)
    # A renamed/reclassified parent campaign cannot unlock another module's preview.
    if "social" not in keys:
        rows = rows.filter(social_review__isnull=True)
    if "email_marketing" not in keys:
        rows = rows.filter(email_review__isnull=True)
    return (
        rows.filter(organization=organization)
        .filter(Q(campaign__service_type="") | Q(campaign__service_type__in=keys))
        .filter(
            Q(social_review__isnull=True)
            | Q(
                social_review__deliverable__client_visible=True,
                social_review__deliverable__content__client_visible=True,
            )
        )
        .filter(
            Q(email_review__isnull=True)
            | Q(
                email_review__deliverable__client_visible=True,
                email_review__deliverable__work__client_visible=True,
            )
        )
    )


def pending_for(actor, organization=None):
    return requests_for(actor, organization).filter(status="pending").order_by("requested_at", "pk")


def campaigns_for(actor, organization):
    if not policies.can_open(actor, organization):
        return Campaign.objects.none()
    rows = Campaign.objects.filter(organization=organization).order_by("name")
    if actor.is_staff_member:
        return rows
    return rows.filter(service_type__in=entitlement_keys(actor, organization=organization))


def detail_for(actor, organization, pk):
    return (
        requests_for(actor, organization)
        .prefetch_related("comments__author", "history__actor")
        .filter(pk=pk)
        .first()
    )
