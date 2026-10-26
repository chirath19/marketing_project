"""Authorisation rules for the Staff domain."""

from __future__ import annotations

from apps.permissions.access import has_permission
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_staff(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("staff", "view"))


def can_manage_staff(actor) -> bool:  # noqa: ANN001
    """Create and edit staff accounts.

    Creating accounts is how someone grants access to the platform, so it
    needs `staff_manage` rather than the softer `staff_edit`.
    """
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("staff", "manage"))


def can_assign_roles(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("staff", "assign"))


def can_assign_clients(actor) -> bool:  # noqa: ANN001
    """Decide whose work a staff member may touch."""
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("organizations", "assign"))
