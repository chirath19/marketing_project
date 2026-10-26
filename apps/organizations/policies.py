"""Authorisation rules for the Organizations domain.

Pure predicates, called from `services.py`, so web, API, admin action and
management command are all covered by the same rule.

The shape of every rule here is the same: staff may act on any client;
a client may act only inside an organization they actively belong to, and
only if their role allows it. Membership is looked up server-side — a
slug or id in a request is never evidence of anything.
"""

from __future__ import annotations

from apps.organizations.models import MANAGING_ROLES
from apps.organizations.selectors import membership_for


def _is_staff(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_staff_member)


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_organization(actor, organization) -> bool:  # noqa: ANN001
    if _is_staff(actor):
        return True
    return membership_for(actor, organization) is not None


def can_manage_organization(actor, organization) -> bool:  # noqa: ANN001
    """Edit the company's own details."""
    if _is_staff(actor):
        return True

    membership = membership_for(actor, organization)
    return bool(membership and membership.role in MANAGING_ROLES)


def can_manage_members(actor, organization) -> bool:  # noqa: ANN001
    """Add people, change their role, remove them."""
    return can_manage_organization(actor, organization)


def can_change_member_role(actor, membership) -> bool:  # noqa: ANN001
    """Change one person's role.

    Nobody changes their own role: an admin must not be able to promote
    themselves to owner, and an owner must not be able to demote
    themselves out of the last owner slot by accident.
    """
    if membership is None:
        return False

    if actor is not None and getattr(actor, "pk", None) == membership.user_id:
        return _is_staff(actor)

    return can_manage_members(actor, membership.organization)


def can_remove_member(actor, membership) -> bool:  # noqa: ANN001
    if membership is None:
        return False

    # Leaving voluntarily is allowed; the "last owner" rule in the
    # service still applies.
    if actor is not None and getattr(actor, "pk", None) == membership.user_id:
        return True

    return can_manage_members(actor, membership.organization)


def can_change_organization_status(actor, organization) -> bool:  # noqa: ANN001
    """Approve, suspend or archive a client company.

    Staff only. A client suspending or reactivating their own account
    would make the status meaningless as a commercial control.
    """
    return _is_staff(actor)


def can_edit_internal_notes(actor, organization) -> bool:  # noqa: ANN001
    """Internal notes are staff-only, in both directions: a client may
    neither write them nor read them."""
    return _is_staff(actor)


def can_delete_organization(actor, organization) -> bool:  # noqa: ANN001
    """Nobody, in practice.

    Archiving is the supported path — the campaigns and reports that
    reference a company must keep their history. Reserved for a super
    admin dealing with a genuine mistake.
    """
    return _is_super_admin(actor)
