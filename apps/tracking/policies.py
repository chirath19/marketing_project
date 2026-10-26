"""Authorisation rules for the Agency Website Tracking domain.

Everything here is about the agency's own website, not any one client,
so there is no object-level half to these checks the way there is for a
client-owned record — only "may this actor see agency-wide analytics
and tag configuration at all."
"""

from __future__ import annotations

from apps.permissions import access
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_website_analytics(actor) -> bool:  # noqa: ANN001
    if _is_super_admin(actor):
        return True
    return access.has_permission(actor, permission_string("analytics", "view"))


def can_configure_tracking(actor) -> bool:  # noqa: ANN001
    if _is_super_admin(actor):
        return True
    return access.has_permission(actor, permission_string("integrations", "manage"))
