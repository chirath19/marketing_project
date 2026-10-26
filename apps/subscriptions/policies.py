"""Authorisation rules for the Subscriptions domain.

Two halves, always. A subscription belongs to a client organization, so
acting on one requires **the permission for the action** *and* **access
to that client** — which is the rule the whole platform is built on, and
the reason `access.can()` takes an object.

Called from `services.py`, so every entry point is covered by the same
check rather than each view remembering to make it.
"""

from __future__ import annotations

from apps.permissions import access
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def _can(actor, action: str, organization=None) -> bool:  # noqa: ANN001
    if _is_super_admin(actor):
        return True

    permission = permission_string("subscriptions", action)
    if organization is None:
        return access.has_permission(actor, permission)

    # Both halves: the right to do it, and access to this client.
    return access.can(actor, permission, organization)


def can_view_subscriptions(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "view", organization)


def can_create_subscriptions(actor, organization=None) -> bool:  # noqa: ANN001
    """Attach a service to a client.

    Deliberately `create` rather than `edit`: putting a client on a
    retainer is a commercial act, and somebody who may correct a typo in
    an existing one should not necessarily be able to start a new one.
    """
    return _can(actor, "create", organization)


def can_edit_subscriptions(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "edit", organization)


def can_change_status(actor, organization=None) -> bool:  # noqa: ANN001
    """Activate, pause, cancel or complete a service.

    Its own right. Pausing a client's advertising stops work and stops
    billing; that is not the same decision as editing a note on it.
    """
    return _can(actor, "approve", organization)


def can_client_see_subscription(actor, subscription) -> bool:  # noqa: ANN001
    """Whether this client may see this service.

    Checked against the row rather than against a list a view built, so
    a guessed URL meets the same rule that filtered the list.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return False

    if actor.is_staff_member:
        return can_view_subscriptions(actor, subscription.organization)

    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    return OrganizationMember.objects.filter(
        organization_id=subscription.organization_id, user=actor,
        status__in=ACTIVE_MEMBERSHIP_STATUSES,
    ).exists()
