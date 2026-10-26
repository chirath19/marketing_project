"""Server-side entitlement for the client portal.

The navigation and these guards read the **same** function. That is the
whole design: a menu that hides a link while the view behind it still
serves the page is not access control, it is decoration — and the first
person to bookmark a URL, or to keep a tab open after their service was
paused, walks straight through it.

So `entitlements()` is the single answer to "what may this client open",
`portal_navigation()` renders it, and `@require_client_module` enforces
it. Change the rule in one place and all three follow.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from apps.core.modules import available_modules, get_module, navigation_for


def entitlements(user, *, organization=None) -> list:  # noqa: ANN001
    """Every portal module this client may open.

    Computed from their **active** services, so pausing a retainer closes
    its area again and cancelling it closes it for good. Staff get
    nothing here: the portal is the client's surface, and staff have
    their own dashboard with its own permissions.
    """
    from apps.subscriptions.models import ClientSubscription

    if (
        not user
        or not getattr(user, "is_authenticated", False)
        or not user.is_active
        or user.is_staff_member
    ):
        return []

    delivering = ClientSubscription.objects.visible_to(user).delivering()
    if organization is not None:
        delivering = delivering.filter(organization=organization)
        if not organization.is_operational:
            delivering = delivering.none()

    service_keys = set(
        delivering.exclude(service__category__workspace_module="").values_list(
            "service__category__workspace_module", flat=True
        )
    )

    modules = available_modules(
        service_keys=service_keys,
        has_any_service=delivering.exists(),
    )

    from apps.core.features import FEATURES, enabled, settings_for

    operating = settings_for(user)
    return [
        module
        for module in modules
        if (key := {"receipts": "payments", "invoices": "payments"}.get(module.key, module.key))
        not in FEATURES
        or enabled(key, operating=operating)
    ]


def entitlement_keys(user, *, organization=None) -> set[str]:  # noqa: ANN001
    return {module.key for module in entitlements(user, organization=organization)}


def can_open_module(user, key: str, *, organization=None) -> bool:  # noqa: ANN001
    """Whether this client is entitled to one specific module."""
    return key in entitlement_keys(user, organization=organization)


def portal_navigation(user, *, organization=None) -> list[dict]:  # noqa: ANN001
    """The sidebar, grouped. Built from the same list the guard uses."""
    return navigation_for(entitlements(user, organization=organization))


def require_client_module(key: str) -> Callable:
    """Refuse a client who is not entitled to this module.

    A 403 rather than a 404, deliberately. The module is a product
    feature whose existence is public — it is on the services page and in
    the price list — so pretending it does not exist would be a lie that
    helps nobody. What is private is *another client's data*, and that is
    guarded separately by the tenancy rule.

    Applied to the view, not checked in the template, so a direct URL,
    a stale bookmark or a script meets exactly the same rule as the menu.
    """
    if get_module(key) is None:  # pragma: no cover - a typo in the registry
        raise ValueError(f"{key!r} is not a portal module.")

    def decorate(view: Callable) -> Callable:
        @wraps(view)
        def guarded(request: HttpRequest, *args, **kwargs):  # noqa: ANN202
            if not can_open_module(request.user, key):
                raise PermissionDenied("Your account does not include this area.")
            return view(request, *args, **kwargs)

        #: Read by the architecture test, which asserts every portal
        #: route declares an entitlement.
        guarded.required_module = key
        return guarded

    return decorate
