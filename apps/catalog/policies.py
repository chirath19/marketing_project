"""Authorisation rules for the service catalogue.

The catalogue belongs to the agency, not to any one client, so these are
permission checks with no organization half.
"""

from __future__ import annotations

from apps.permissions.access import has_permission
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_catalog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("catalog", "view"))


def can_create_catalog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("catalog", "create"))


def can_edit_catalog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("catalog", "edit"))


def can_delete_catalog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("catalog", "delete"))


def can_publish_catalog(actor) -> bool:  # noqa: ANN001
    """Put a service in front of the public.

    Separate from editing, as it is for pages and posts: preparing a
    service and deciding it is ready to sell are different decisions.
    """
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("catalog", "publish"))
