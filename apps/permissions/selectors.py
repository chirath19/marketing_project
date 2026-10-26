"""Read access for the Roles and Permissions domain."""

from __future__ import annotations

from django.db.models import Count, QuerySet

from apps.permissions import policies
from apps.permissions.models import Role


def visible_roles(actor) -> QuerySet:  # noqa: ANN001
    """Roles the actor may list.

    Role configuration is platform-wide, so this is all-or-nothing behind
    the permission. Annotated with the permission count so rendering the
    list does not issue one count per row.
    """
    if not policies.can_view_roles(actor):
        return Role.objects.none()

    return (
        Role.objects.annotate(permission_count=Count("permissions", distinct=True))
        .order_by("name")
    )


def get_role(actor, pk: int):  # noqa: ANN001, ANN201
    return (
        visible_roles(actor)
        .prefetch_related("permissions")
        .filter(pk=pk)
        .first()
    )


def role_permission_matrix(role: Role, actor=None) -> list[dict]:
    """The role's permissions laid out module by module, for a settings page."""
    from apps.permissions.catalogue import MODULES

    held = role.permission_codenames
    return [
        {
            "module": module,
            "actions": [
                {
                    "action": action,
                    "codename": f"{module.key}_{action}",
                    "held": f"{module.key}_{action}" in held,
                }
                for action in module.actions
            ],
        }
        for module in MODULES
        if actor is None or actor.is_super_admin or any(
            actor.has_perm(f"permissions.{module.key}_{action}") for action in module.actions)
    ]
