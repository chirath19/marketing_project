"""Access combines client assignment, current membership, and a named recipient."""

from apps.organizations.selectors import membership_for
from apps.permissions.access import can


def may_access(actor, organization, client, permission="messaging_view"):
    from apps.core.features import visible

    feature = {"messaging": "messages", "analytics": "reports", "subscriptions": "payments"}.get(
        permission.rsplit("_", 1)[0], "messages"
    )
    if not visible(feature, actor):
        return False
    if not actor.is_authenticated or not actor.is_active or not client.is_client:
        return False
    if not membership_for(client, organization) or organization.status != "active":
        return False
    if actor.is_staff_member:
        return can(actor, permission, organization)
    return actor.pk == client.pk and bool(membership_for(actor, organization))
