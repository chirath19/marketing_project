"""DRF integration.

The API is held to exactly the same rule as the web views — the same
`access.can()` — rather than to a parallel set of checks that could drift.
"""

from __future__ import annotations

from rest_framework import permissions

from apps.permissions import access
from apps.permissions.catalogue import APP_LABEL


class HasPlatformPermission(permissions.BasePermission):
    """Require a platform permission, and client access for object views.

    Set `required_permission` on the view, or `required_permissions` as a
    mapping of HTTP method to permission when the verbs differ::

        class CampaignViewSet(ModelViewSet):
            permission_classes = [HasPlatformPermission]
            required_permissions = {
                "GET": "campaigns_view",
                "POST": "campaigns_create",
                "PATCH": "campaigns_edit",
                "DELETE": "campaigns_delete",
            }

    `has_object_permission` repeats the check with the object in hand,
    which is where the client-access half applies. DRF only calls it for
    detail routes, so list endpoints must also narrow their queryset with
    `guards.scope_to_accessible` — a permission check cannot filter rows.
    """

    message = "You do not have permission to do that."

    def _permission_for(self, request, view) -> str | None:  # noqa: ANN001
        mapping = getattr(view, "required_permissions", None)
        if mapping:
            perm = mapping.get(request.method)
            if perm:
                return perm
            # An unmapped method is refused rather than allowed: a new
            # verb must be considered, not inherited.
            return None
        return getattr(view, "required_permission", None)

    @staticmethod
    def _qualify(perm: str) -> str:
        return perm if "." in perm else f"{APP_LABEL}.{perm}"

    def has_permission(self, request, view) -> bool:  # noqa: ANN001
        user = request.user
        if not user or not user.is_authenticated:
            return False

        perm = self._permission_for(request, view)
        if not perm:
            return False

        return access.can(user, self._qualify(perm))

    def has_object_permission(self, request, view, obj) -> bool:  # noqa: ANN001
        perm = self._permission_for(request, view)
        if not perm:
            return False
        return access.can(request.user, self._qualify(perm), obj)
