"""Authorisation rules for the Campaigns domain.

Two halves, always: **the permission for the action** and **access to
that client**. A specialist assigned to three clients holds
`campaigns_edit` for all of them and must not be able to touch a fourth
client's campaign by typing its id.

Called from `services.py`, so every entry point — a staff view, a future
SEO module, an API, a management command — is covered by the same rule
rather than each remembering to make it.
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

    permission = permission_string("campaigns", action)
    if organization is None:
        return access.has_permission(actor, permission)

    return access.can(actor, permission, organization)


def can_view_campaigns(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "view", organization)


def can_create_campaigns(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "create", organization)


def can_edit_campaigns(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "edit", organization)


def can_assign_campaigns(actor, organization=None) -> bool:  # noqa: ANN001
    """Decide who works on a campaign.

    Its own right, as with leads and quotes: handing out work is a
    different decision from doing it.
    """
    return _can(actor, "assign", organization)


def can_change_status(actor, organization=None) -> bool:  # noqa: ANN001
    """Take a campaign live, pause it or stop it.

    Guarded by `approve` rather than `edit`: putting a client's
    advertising live commits their budget, and that is not the same
    decision as correcting a description.
    """
    return _can(actor, "approve", organization)


def can_client_see_campaign(actor, campaign) -> bool:  # noqa: ANN001
    """Whether this client may see this campaign.

    Checked against the row rather than a list a view built, so a
    guessed URL meets the same rule that filtered the list.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    if not area_available(actor, campaign.service_type):
        return False

    if actor.is_staff_member:
        return can_view_campaigns(actor, campaign.organization)

    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    return OrganizationMember.objects.filter(
        organization_id=campaign.organization_id, user=actor,
        status__in=ACTIVE_MEMBERSHIP_STATUSES,
    ).exists()


def area_available(actor, service_type):
    from apps.core.features import FEATURES, visible

    return service_type not in FEATURES or visible(service_type, actor)
