"""The platform's authentication and permission backend.

One backend, deliberately. Django resolves `has_perm` as a union across
backends — if any backend says yes, the answer is yes — so leaving
`ModelBackend` alongside this one would make a deny override
unenforceable: a permission withheld here could be re-granted through a
Django group, and the control would be decorative.

So this *is* `ModelBackend`, subclassed. Authentication is unchanged and
still strict (only an ACTIVE account can sign in). Permission checks are
split in two:

* `permissions.*` — the platform's own vocabulary, resolved through
  roles, overrides and client assignments by `access.py`;
* everything else — Django's own model permissions, left to Django, so
  the admin keeps working for the people who need it.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.backends import ModelBackend

from apps.permissions import access
from apps.permissions.catalogue import APP_LABEL


class PlatformPermissionBackend(ModelBackend):
    """Authentication from Django, authorisation from this platform."""

    @staticmethod
    def _is_platform_permission(perm: str) -> bool:
        return isinstance(perm, str) and perm.startswith(f"{APP_LABEL}.")

    def has_perm(self, user_obj, perm: str, obj: Any = None) -> bool:  # noqa: ANN001
        if not self._is_platform_permission(perm):
            # A Django model permission — `accounts.change_user` and the
            # like. Django's own resolution still applies, which is what
            # keeps the admin usable.
            return super().has_perm(user_obj, perm, obj=obj)

        if not getattr(user_obj, "is_active", False):
            return False

        # The whole question: the right action, on a client this person
        # may reach.
        return access.can(user_obj, perm, obj)

    def get_all_permissions(self, user_obj, obj: Any = None) -> set[str]:  # noqa: ANN001
        """Every permission the user holds, Django's and the platform's.

        Used by `{{ perms }}` in templates and by the admin. With an
        object in play the platform half is filtered by client access, so
        a template cannot show a control for a client the user may not
        touch.
        """
        if not getattr(user_obj, "is_active", False):
            return set()

        django_permissions = super().get_all_permissions(user_obj, obj=obj)

        platform = {
            f"{APP_LABEL}.{codename}"
            for codename in access.permission_codenames_for(user_obj)
        }

        if obj is not None:
            platform = {perm for perm in platform
                        if access.can(user_obj, perm, obj)}

        return django_permissions | platform
