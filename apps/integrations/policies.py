"""Authorisation rules for the Integrations domain.

Connections and sync runs are mostly agency-wide configuration — a staff
member either may manage integrations or may not, there is usually no
per-client half to the decision. The one place a client *is* relevant is
`can_view_connection`, because a connection does carry one client's
account identifiers, and a specialist assigned elsewhere has no business
reading them.
"""

from __future__ import annotations

from apps.permissions import access
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_integrations(actor) -> bool:  # noqa: ANN001
    if _is_super_admin(actor):
        return True
    return access.has_permission(actor, permission_string("integrations", "view"))


def can_manage_integrations(actor) -> bool:  # noqa: ANN001
    if _is_super_admin(actor):
        return True
    return access.has_permission(actor, permission_string("integrations", "manage"))


def can_view_connection(actor, connection) -> bool:  # noqa: ANN001
    """Whether this connection's client falls within this actor's reach.

    An agency-wide connection (`organization` is `None`) has no client to
    check against, so holding the module permission is the whole answer.
    """
    if not can_view_integrations(actor):
        return False
    if connection.organization_id is None:
        return True
    return access.can(actor, permission_string("integrations", "view"),
                      connection.organization)
