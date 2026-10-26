"""Approval permissions plus current organization, entitlement and source visibility."""

from apps.organizations.selectors import membership_for
from apps.permissions import access
from apps.subscriptions.guards import can_open_module


def can_open(actor, organization=None):
    if not actor or not actor.is_authenticated or not actor.is_active:
        return False
    if actor.is_staff_member:
        return (
            access.can(actor, "permissions.approvals_view", organization)
            if organization
            else access.has_permission(actor, "permissions.approvals_view")
        )
    return bool(
        organization
        and organization.is_operational
        and membership_for(actor, organization)
        and can_open_module(actor, "approvals", organization=organization)
    )


def can_read(actor, request):
    if not can_open(actor, request.organization):
        return False
    if actor.is_staff_member:
        return True
    if request.source_module and not can_open_module(
        actor, request.source_module, organization=request.organization
    ):
        return False
    if request.campaign.service_type and not can_open_module(
        actor, request.campaign.service_type, organization=request.organization
    ):
        return False
    if request.social_review_id:
        delivery = request.social_review.deliverable
        return delivery.client_visible and delivery.content.client_visible
    if request.email_review_id:
        delivery = request.email_review.deliverable
        return delivery.client_visible and delivery.work.client_visible
    return True


def can_create(actor, organization):
    return can_open(actor, organization) and access.can(
        actor, "permissions.approvals_create", organization
    )


def can_respond(actor, request):
    if not can_read(actor, request) or actor.is_staff_member:
        return False
    return membership_for(actor, request.organization).role in {"owner", "admin", "member"}


def can_comment(actor, request):
    if not can_read(actor, request):
        return False
    if actor.is_staff_member:
        return access.can(
            actor, "permissions.approvals_create", request.organization
        ) or access.can(actor, "permissions.approvals_approve", request.organization)
    return can_respond(actor, request)


def can_cancel(actor, request):
    return can_read(actor, request) and access.can(
        actor, "permissions.approvals_approve", request.organization
    )
