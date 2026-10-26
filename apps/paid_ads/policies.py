"""Action permission plus assignment; clients have a separate read-only path."""

from apps.permissions import access


def can_write(actor, organization, action="create"):
    return access.can(actor, f"permissions.paid_ads_{action}", organization)


def can_read(actor, organization):
    if not actor or not actor.is_authenticated or not actor.is_active or not organization:
        return False
    if actor.is_staff_member:
        return access.can(actor, "permissions.paid_ads_view", organization)
    from apps.organizations.selectors import membership_for
    from apps.subscriptions.guards import can_open_module

    return bool(
        organization.is_operational
        and membership_for(actor, organization)
        and can_open_module(actor, "paid_ads", organization=organization)
    )
