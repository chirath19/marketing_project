"""Authorisation rules for the SEO domain.

Two halves, always: **the permission for the action** and **access to
that client**. The same shape as every other delivery domain, because an
SEO specialist assigned to three clients holds `seo_edit` for all of them
and must not reach a fourth by typing an id.

Called from `services.py`, so every entry point is covered by one rule
rather than each view remembering to make it.
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

    permission = permission_string("seo", action)
    if organization is None:
        return access.has_permission(actor, permission)

    return access.can(actor, permission, organization)


def can_view_seo(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "view", organization)


def can_create_seo(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "create", organization)


def can_edit_seo(actor, organization=None) -> bool:  # noqa: ANN001
    return _can(actor, "edit", organization)


def can_deliver_seo(actor, organization=None) -> bool:  # noqa: ANN001
    """Publish an audit to the client.

    Its own right. Everything in an audit is internal until somebody
    decides it is ready to be read by the client, and that decision is
    not the same as editing a finding.
    """
    return _can(actor, "approve", organization)


def can_client_see(actor, record) -> bool:  # noqa: ANN001
    """Whether this client may see this SEO record.

    Checked against the row rather than a list a view built, so a guessed
    URL meets the same rule that filtered the list.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return False

    if actor.is_staff_member:
        return can_view_seo(actor, record.organization)

    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    return OrganizationMember.objects.filter(
        organization_id=record.organization_id, user=actor,
        status__in=ACTIVE_MEMBERSHIP_STATUSES,
    ).exists()
