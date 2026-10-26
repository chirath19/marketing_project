"""Read conversations and per-client workspace recipients."""

from django.contrib.auth import get_user_model

from apps.messaging.models import Conversation
from apps.messaging.policies import may_access
from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember
from apps.permissions.guards import scope_to_accessible


def recipients(actor):
    if not actor.is_staff_member:
        return OrganizationMember.objects.none()
    return (
        scope_to_accessible(
            OrganizationMember.objects.filter(
                status__in=ACTIVE_MEMBERSHIP_STATUSES,
                organization__status="active",
                user__user_type="client",
                user__status="active",
            ),
            actor,
        )
        .select_related("user", "organization")
        .order_by("organization__name", "user__full_name")
    )


def recipient(actor, organization, user_id):
    client = get_user_model().objects.filter(pk=user_id, user_type="client").first()
    if client and any(
        may_access(actor, organization, client, permission)
        for permission in ("messaging_view", "analytics_view", "subscriptions_view")
    ):
        return client
    return None


def conversation(actor, organization, client):
    if not may_access(actor, organization, client):
        return None
    return Conversation.objects.filter(organization=organization, client=client).first()
