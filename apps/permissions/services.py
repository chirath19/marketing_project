"""Write operations for roles and permission overrides."""

from __future__ import annotations

import logging

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.core.events import DomainEvent, bus
from apps.permissions import access, policies
from apps.permissions.catalogue import all_codenames, catalogue_filter
from apps.permissions.models import (
    OverrideEffect,
    Role,
    RolePermission,
    UserPermissionOverride,
)

logger = logging.getLogger(__name__)


def _permissions_for(codenames) -> list[Permission]:  # noqa: ANN001
    """Resolve codenames to Permission rows, refusing anything unknown.

    A typo must not silently produce a role with fewer rights than whoever
    configured it believed.
    """
    wanted = list(dict.fromkeys(codenames))
    unknown = [name for name in wanted if name not in set(all_codenames())]
    if unknown:
        raise ValidationError(f"Unknown permission(s): {sorted(unknown)}")

    found = list(Permission.objects.filter(**catalogue_filter(), codename__in=wanted))
    missing = set(wanted) - {permission.codename for permission in found}
    if missing:
        raise ValidationError(
            f"Permission(s) not created yet: {sorted(missing)}. "
            "Run `manage.py sync_permissions`."
        )
    return found


@transaction.atomic
def create_role(*, name: str, actor, description: str = "",
                permissions: list[str] | None = None,
                is_system: bool = False) -> Role:
    if not policies.can_manage_roles(actor):
        raise PermissionDenied("You may not manage roles.")

    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationError("A role needs a name.")

    if Role.objects.filter(name__iexact=cleaned).exists():
        raise ValidationError(f"A role called {cleaned!r} already exists.")

    role = Role.objects.create(
        name=cleaned, slug=slugify(cleaned)[:140],
        description=description.strip(), is_system=is_system,
    )

    if permissions:
        set_role_permissions(role=role, codenames=permissions, actor=actor)

    bus.publish(DomainEvent("role.created", {
        "role_id": role.pk, "name": role.name,
        "actor_id": getattr(actor, "pk", None),
    }))
    logger.info("Role created: %s", role.name)
    return role


@transaction.atomic
def update_role(*, role: Role, actor, name: str | None = None,
                description: str | None = None) -> Role:
    if not policies.can_manage_roles(actor):
        raise PermissionDenied("You may not manage roles.")

    changed = []
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("A role needs a name.")
        if Role.objects.filter(name__iexact=cleaned).exclude(pk=role.pk).exists():
            raise ValidationError(f"A role called {cleaned!r} already exists.")
        if role.name != cleaned:
            role.name = cleaned
            changed.append("name")

    if description is not None and role.description != description.strip():
        role.description = description.strip()
        changed.append("description")

    if changed:
        role.save(update_fields=[*changed, "updated_at"])
    return role


@transaction.atomic
def set_role_permissions(*, role: Role, codenames: list[str], actor) -> Role:
    """Replace a role's permissions with exactly this set.

    Replace rather than merge: a configuration screen that posts the
    checked boxes must be able to *remove* a permission by unchecking it.
    """
    if not policies.can_manage_roles(actor):
        raise PermissionDenied("You may not manage roles.")

    if not actor.is_super_admin:
        held = access.permission_codenames_for(actor)
        if not set(codenames) <= held or not role.permission_codenames <= held:
            raise PermissionDenied("You may only manage permissions within your own authority.")
    wanted = _permissions_for(codenames)
    wanted_ids = {permission.pk for permission in wanted}
    current_ids = set(
        RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
    )

    RolePermission.objects.filter(
        role=role, permission_id__in=current_ids - wanted_ids
    ).delete()

    RolePermission.objects.bulk_create([
        RolePermission(role=role, permission_id=permission_id,
                       granted_by=actor if getattr(actor, "pk", None) else None)
        for permission_id in wanted_ids - current_ids
    ])

    if current_ids != wanted_ids:
        bus.publish(DomainEvent("role.permissions_changed", {
            "role_id": role.pk,
            "added": sorted(wanted_ids - current_ids),
            "removed": sorted(current_ids - wanted_ids),
            "actor_id": getattr(actor, "pk", None),
        }))
        logger.info("Role %s permissions changed", role.name)

    return role


@transaction.atomic
def delete_role(*, role: Role, actor) -> None:
    if not policies.can_manage_roles(actor):
        raise PermissionDenied("You may not manage roles.")

    if role.is_system:
        raise ValidationError(
            "System roles ship with the platform and cannot be deleted. "
            "Edit its permissions instead."
        )

    name = role.name
    role.delete()
    bus.publish(DomainEvent("role.deleted", {
        "name": name, "actor_id": getattr(actor, "pk", None),
    }))


# ---------------------------------------------------------------------------
# Per-user overrides
# ---------------------------------------------------------------------------


@transaction.atomic
def set_override(*, user, permission_codename: str, effect: str, actor,  # noqa: ANN001
                 reason: str = "") -> UserPermissionOverride:
    """Grant or deny one permission to one person.

    An override replaces any previous one for the same permission: one
    answer per person per permission, or a grant and a deny could both be
    true at once.
    """
    if not policies.can_manage_overrides(actor):
        raise PermissionDenied("You may not manage permission overrides.")

    if effect not in OverrideEffect.values:
        raise ValidationError(f"{effect!r} is not a valid override effect.")

    if not user.is_staff_member:
        raise ValidationError(
            "Permission overrides apply to staff. A client's rights come "
            "from their membership of their own organization."
        )

    permission = _permissions_for([permission_codename])[0]

    override, _created = UserPermissionOverride.objects.update_or_create(
        user=user, permission=permission,
        defaults={
            "effect": effect, "reason": reason.strip()[:255],
            "granted_by": actor if getattr(actor, "pk", None) else None,
        },
    )

    access.clear_cache(user)
    bus.publish(DomainEvent("permission.override_set", {
        "user_id": user.pk, "permission": permission.codename,
        "effect": effect, "actor_id": getattr(actor, "pk", None),
    }))
    logger.info("Override: %s %s %s", user.email, effect, permission.codename)
    return override


@transaction.atomic
def clear_override(*, user, permission_codename: str, actor) -> None:  # noqa: ANN001
    if not policies.can_manage_overrides(actor):
        raise PermissionDenied("You may not manage permission overrides.")

    UserPermissionOverride.objects.filter(
        user=user, permission__codename=permission_codename,
        permission__content_type__app_label="permissions",
        permission__content_type__model="platformpermission",
    ).delete()
    access.clear_cache(user)
