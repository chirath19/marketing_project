"""Guards for every protected entry point.

Web views, API endpoints, exports and downloads all go through the same
`access.can()` call, so there is one rule and not four slightly different
ones. The guard is applied on the server in every case; a hidden button
is presentation, never a control.

    @require_permission("seo_edit")
    def edit_campaign(request, pk): ...

    @require_permission("organizations_export")
    def export_clients(request): ...

    @require_permission("organizations_view", lookup=campaign_organization)
    def campaign_detail(request, pk): ...

The `lookup` form is what makes an object endpoint safe: it resolves the
object first and checks the permission *against that object*, so a staff
member with the right permission but no assignment to that client is
refused.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from apps.permissions import access
from apps.permissions.catalogue import APP_LABEL


def _as_permission_string(perm: str) -> str:
    return perm if "." in perm else f"{APP_LABEL}.{perm}"


def require_permission(
    perm: str,
    lookup: Callable[[HttpRequest, Any], Any] | None = None,
) -> Callable:
    """Refuse the request unless the actor may perform this action.

    An anonymous visitor is sent to sign in; a signed-in user without the
    right is refused with 403. The distinction matters: redirecting a
    signed-in user to a login page they are already past is a confusing
    dead end.

    `lookup(request, *args, **kwargs)` returns the object the action is
    performed on. The permission is then checked against it, which brings
    in the client-access half.
    """
    permission = _as_permission_string(perm)

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            user = getattr(request, "user", None)

            if user is None or not user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            obj = lookup(request, *args, **kwargs) if lookup else None

            if not access.can(user, permission, obj):
                raise PermissionDenied(
                    "You do not have permission to do that."
                )

            if obj is not None:
                # Handed to the view so it does not fetch the same row
                # twice, and so the view cannot accidentally act on a
                # different object than the one that was authorised.
                request.authorised_object = obj

            return view(request, *args, **kwargs)

        return wrapper

    return decorator


class PermissionRequiredMixin:
    """Class-based view form of `require_permission`.

    Set `required_permission`, and optionally override `get_authorised_object`
    to bring the object — and therefore the client — into the check.
    """

    required_permission: str = ""

    def get_authorised_object(self):  # noqa: ANN201
        return None

    def dispatch(self, request: HttpRequest, *args, **kwargs):  # noqa: ANN201
        if not self.required_permission:
            raise ValueError(
                f"{type(self).__name__} must set `required_permission`."
            )

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        self.args, self.kwargs, self.request = args, kwargs, request
        obj = self.get_authorised_object()

        if not access.can(user, _as_permission_string(self.required_permission), obj):
            raise PermissionDenied("You do not have permission to do that.")

        return super().dispatch(request, *args, **kwargs)


def ensure_can(user, perm: str, obj: Any = None) -> None:  # noqa: ANN001
    """Raise unless the actor may act. For use inside a service or a view body."""
    if not access.can(user, _as_permission_string(perm), obj):
        raise PermissionDenied("You do not have permission to do that.")


def scope_to_accessible(queryset, user, *, field: str = "organization_id"):  # noqa: ANN001
    """Narrow a queryset to the clients this actor may reach.

    The companion to `require_permission` for list and export endpoints:
    the permission says they may export clients, this says *which* clients
    end up in the file. Without it an export is a quiet way around every
    object-level check.
    """
    allowed = access.accessible_organization_ids(user)
    if allowed is None:
        return queryset
    return queryset.filter(**{f"{field}__in": allowed})


def require_staff_member(view: Callable) -> Callable:
    """Refuse anyone who is not agency staff.

    For the few dashboard surfaces that are not about one capability — the
    home page, global search. They still need a server-side guard: a
    client must not be able to open the staff shell at all, however little
    it would show them.
    """

    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if not user.is_active or not user.is_staff_member:
            raise PermissionDenied("This area is for agency staff.")

        return view(request, *args, **kwargs)

    return wrapper
