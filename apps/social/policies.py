"""Staff action permissions and assignment; client membership and review roles."""

from apps.permissions import access


def can_write(actor, organization, action="create"):
    return access.can(actor, f"permissions.social_{action}", organization)


def can_read(actor, organization):
    if not actor or not actor.is_authenticated or not actor.is_active or not organization:
        return False
    if actor.is_staff_member:
        return access.can(actor, "permissions.social_view", organization)
    from apps.organizations.selectors import membership_for
    from apps.subscriptions.guards import can_open_module

    return bool(
        organization.is_operational
        and membership_for(actor, organization)
        and can_open_module(actor, "social", organization=organization)
    )


def can_review(actor, organization):
    from apps.organizations.selectors import membership_for

    if not can_read(actor, organization) or actor.is_staff_member:
        return False
    membership = membership_for(actor, organization)
    return membership.role in {"owner", "admin", "member"}
