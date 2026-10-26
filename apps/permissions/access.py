"""Access resolution.

One question, one answer, one place:

    may this actor perform this action on this object?

which is always two things at once —

    permission to perform the action
    AND
    access to the client organization the object belongs to

Resolution order for the permission half, strictest first:

    1. deny override        — wins over everything, including roles
    2. grant override       — a personal exception a role cannot express
    3. role permissions     — the usual path
    4. otherwise denied     — the default is closed

Results are memoised on the user object for the life of the request. The
cache is deliberately per-object rather than global: a permission change
must take effect on the very next request, and the brief rules out Redis,
so there is nothing to invalidate across processes.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import Permission

from apps.permissions.catalogue import catalogue_filter, is_client_scoped

logger = logging.getLogger(__name__)

_PERMISSION_CACHE = "_platform_permission_cache"
_ORGANIZATION_CACHE = "_platform_organization_cache"


# ---------------------------------------------------------------------------
# The permission half
# ---------------------------------------------------------------------------


def _strip(perm: str) -> str:
    """`permissions.seo_edit` → `seo_edit`."""
    return perm.split(".", 1)[-1] if "." in perm else perm


def permission_codenames_for(user) -> frozenset[str]:  # noqa: ANN001
    """Every platform permission this user actually holds."""
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()

    cached = getattr(user, _PERMISSION_CACHE, None)
    if cached is not None:
        return cached

    resolved = _resolve_permissions(user)
    # Resolve feature availability alongside permissions, once per request.
    from apps.core.features import settings_for

    settings_for(user)
    setattr(user, _PERMISSION_CACHE, resolved)
    return resolved


def _resolve_permissions(user) -> frozenset[str]:  # noqa: ANN001
    from apps.permissions.models import OverrideEffect, UserPermissionOverride

    # A super admin holds everything by definition; there is no bundle to
    # resolve and no override that applies to them.
    if user.is_super_admin:
        return frozenset(
            Permission.objects.filter(**catalogue_filter())
            .values_list("codename", flat=True)
        )

    if not user.is_staff_member:
        # Clients do not hold platform permissions. Their rights come from
        # their membership role inside their own organization, which is a
        # different mechanism in apps.organizations.
        return frozenset()

    granted: set[str] = set()
    if user.is_system_owner:
        from apps.permissions.catalogue import all_codenames

        granted.update(key for key in all_codenames() if not key.startswith("settings_"))

    profile = getattr(user, "staff_profile", None)
    if profile is not None:
        granted.update(
            Permission.objects.filter(
                platform_roles__staff_profiles=profile,
                **catalogue_filter(),
            ).values_list("codename", flat=True)
        )

    overrides = (
        UserPermissionOverride.objects.filter(user=user)
        .select_related("permission")
        .values_list("permission__codename", "effect")
    )

    denied = set()
    for codename, effect in overrides:
        if effect == OverrideEffect.DENY:
            denied.add(codename)
        else:
            granted.add(codename)

    # Deny last, so it overrides both the roles and a grant override.
    return frozenset(granted - denied)


def has_permission(user, perm: str) -> bool:  # noqa: ANN001
    """The permission half alone, with no object in play."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active:
        return False
    from apps.core.features import permission_available

    if not permission_available(user, _strip(perm)):
        return False
    return _strip(perm) in permission_codenames_for(user)


# ---------------------------------------------------------------------------
# The client-access half
# ---------------------------------------------------------------------------


def accessible_organization_ids(user) -> frozenset[int] | None:  # noqa: ANN001
    """Client organizations this actor may reach.

    Returns None to mean "every client", which is not the same as an
    empty set — the difference between a head of delivery and a new
    starter with no accounts yet.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()

    cached = getattr(user, _ORGANIZATION_CACHE, "missing")
    if cached != "missing":
        return cached

    resolved = _resolve_organizations(user)
    setattr(user, _ORGANIZATION_CACHE, resolved)
    return resolved


def _resolve_organizations(user) -> frozenset[int] | None:  # noqa: ANN001
    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember
    from apps.staff.models import ACCESS_GRANTING_STATUSES, StaffClientAssignment

    if user.is_super_admin or user.is_system_owner:
        return None

    if user.is_staff_member:
        profile = getattr(user, "staff_profile", None)
        if profile is not None and profile.has_all_client_access:
            return None

        return frozenset(
            StaffClientAssignment.objects.filter(
                staff__user=user, status__in=ACCESS_GRANTING_STATUSES,
            ).values_list("organization_id", flat=True)
        )

    # A client reaches their own organizations through membership.
    return frozenset(
        OrganizationMember.objects.filter(
            user=user, status__in=ACTIVE_MEMBERSHIP_STATUSES,
        ).values_list("organization_id", flat=True)
    )


def can_access_organization(user, organization) -> bool:  # noqa: ANN001
    if organization is None:
        return False

    allowed = accessible_organization_ids(user)
    if allowed is None:
        return True

    organization_id = getattr(organization, "pk", organization)
    return organization_id in allowed


# ---------------------------------------------------------------------------
# Finding the organization an object belongs to
# ---------------------------------------------------------------------------


def organization_of(obj: Any):  # noqa: ANN201
    """The organization an object belongs to, or its id, or None.

    Either form is accepted by `can_access_organization`, and reading
    `organization_id` rather than `organization` means resolving an
    object's owner costs no extra query. None means the object is not
    client data.
    """
    if obj is None:
        return None

    from apps.organizations.models import Organization

    if isinstance(obj, Organization):
        return obj

    if hasattr(obj, "organization_id"):
        return obj.organization_id

    # A membership, an assignment — anything that reaches an organization
    # one step away.
    organization = getattr(obj, "organization", None)
    return organization


# ---------------------------------------------------------------------------
# The whole question
# ---------------------------------------------------------------------------


def can(user, perm: str, obj: Any = None) -> bool:  # noqa: ANN001
    """Permission to perform the action AND access to the client.

    With no object, only the permission half is checked — which is right
    for "may this person open the campaigns section at all", and wrong as
    the only check before touching a specific campaign. Pass the object.
    """
    if not has_permission(user, perm):
        return False

    if obj is None:
        return True

    # Platform-wide areas — the service catalogue, system settings, the
    # staff list — belong to no client, so there is nothing to scope to.
    if not is_client_scoped(perm):
        return True

    organization = organization_of(obj)
    if organization is None:
        # The object is not client data. Falling back to the permission
        # alone is correct here and is why `is_client_scoped` above is
        # checked first: an unknown *permission* is treated as scoped.
        return True

    return can_access_organization(user, organization)


def clear_cache(user) -> None:  # noqa: ANN001
    """Forget a user's resolved access.

    Called by the services that change roles, overrides or assignments so
    that a change takes effect within the same request, not just the next
    one.
    """
    for attribute in (_PERMISSION_CACHE, _ORGANIZATION_CACHE):
        if hasattr(user, attribute):
            delattr(user, attribute)
