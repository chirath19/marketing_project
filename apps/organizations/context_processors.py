"""Client chrome for every template.

Two things: the organization the current session is working in, and the
portal navigation built from what that client has bought.

Both are resolved lazily. Staff pages, the public site, the API and the
health check all run these too, and none of them should pay for a query
it will never read.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject


def organization(request: HttpRequest) -> dict:
    """The organization this session is working in, or None for staff.

    Read straight off the request, where the middleware put it — so a
    template and a view can never disagree about which client is in
    scope.
    """
    return {
        "organization": SimpleLazyObject(
            lambda: getattr(request, "organization", None)
        ),
        "available_organizations": SimpleLazyObject(
            lambda: _available(request)
        ),
    }


def _available(request: HttpRequest):  # noqa: ANN202
    """Organizations this user can switch between.

    An empty list for staff and for anyone signed out, so the switcher
    simply does not render rather than each template testing for it.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.is_staff_member:
        return []

    from apps.organizations import selectors

    return list(selectors.organizations_for_user(user))


def portal_chrome(request: HttpRequest) -> dict:
    """The client portal's sidebar, grouped.

    Built once, here, rather than in each view — so a page added later
    cannot render a navigation that disagrees with what the route guards
    allow. Both read `apps.subscriptions.guards.entitlements`.
    """
    def navigation():  # noqa: ANN202
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or user.is_staff_member:
            return []

        from apps.subscriptions.guards import portal_navigation

        return portal_navigation(user, organization=request.organization or None)

    return {"portal_nav": SimpleLazyObject(navigation)}
