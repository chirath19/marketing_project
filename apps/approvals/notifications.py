"""Transactional, per-recipient in-app notifications only. No mail or SMS transport."""

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.approvals import policies
from apps.notifications.services import notify
from apps.organizations.selectors import members_of
from apps.permissions import access


def changed(request, actor, *, commented=False):
    recipients = {
        member.user_id: member.user
        for member in members_of(actor, request.organization)
        if member.user.is_active and member.status == "active"
    }
    for user in (
        get_user_model()
        .objects.filter(status="active", user_type__in=["staff", "super_admin"])
        .select_related("staff_profile")
    ):
        if policies.can_read(user, request):
            recipients[user.pk] = user
    # Domain staff may request a review without access to the shared staff inbox.
    requester = request.requested_by
    fallback = None
    if (
        request.source_module
        and requester.is_active
        and access.can(requester, f"permissions.{request.source_module}_view", request.organization)
    ):
        recipients[requester.pk] = requester
        parent = (
            request.social_review.deliverable.content
            if request.social_review_id
            else request.email_review.deliverable.work
        )
        fallback = reverse(
            f"staff:{request.source_module}_detail", args=[request.organization.slug, parent.pk]
        )
    for user in recipients.values():
        if user.pk == actor.pk:
            continue
        if policies.can_read(user, request):
            namespace = "staff" if user.is_staff_member else "organizations"
            url = reverse(f"{namespace}:approval_detail", args=[request.pk])
        elif user.pk == requester.pk and fallback:
            url = fallback
        else:
            continue
        # Keep notifications as pointers, so revoked sharing never leaves a copy of sensitive copy.
        notify(
            recipient=user,
            title="Approval comment added"
            if commented
            else f"Approval {request.get_status_display().lower()}",
            body="Open the approval to see its current details.",
            url=url,
            level="action" if request.status == "pending" else "info",
            category="approval",
        )
