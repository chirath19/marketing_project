"""Authorisation rules for the Roles and Permissions domain.

Who may change the rules is itself a rule, and a conservative one:
reassigning permissions is how a limited account becomes an unlimited
one, so it is reserved for super admins and for staff explicitly granted
`roles_manage`.
"""

from __future__ import annotations

from apps.permissions.access import has_permission
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_roles(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("roles", "view"))


def can_manage_roles(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("roles", "manage"))


def can_manage_overrides(actor) -> bool:  # noqa: ANN001
    """Grant or withhold a permission from one person.

    Super admins only. An override is the sharpest tool here — it beats
    every role — and letting it be delegated through a role would make the
    role hierarchy circular.
    """
    return _is_super_admin(actor)


def can_assign_roles(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("staff", "assign"))
