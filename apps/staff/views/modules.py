"""Pages for navigation sections whose module is not built yet.

Every one is a real route, guarded by its real permission, so the
authorisation model is complete and testable before the features land.
What they render is an honest statement that the module does not exist —
not a mock-up, and certainly not invented data. A dashboard that shows
plausible-looking numbers during development is one nobody trusts
afterwards.

Each page becomes a real one by replacing its entry here with a view in
the owning domain. The nav entry, the permission and the tests do not
change.
"""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.permissions.guards import require_permission
from apps.staff.navigation import item_for


def _placeholder(request: HttpRequest, key: str) -> HttpResponse:
    item = item_for(key)
    if item is None:  # pragma: no cover - the registry is static
        raise Http404

    return render(request, "admin/module_placeholder.html", {
        "page_title": item.label,
        "page_subtitle": item.description,
        "nav_key": item.key,
        "item": item,
        "breadcrumbs": [{"label": "Dashboard", "href": "/staff/dashboard/"}],
    })


@require_permission("subscriptions_view")
def subscriptions(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "subscriptions")


@require_permission("approvals_view")
def approvals(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "approvals")


@require_permission("campaigns_view")
def campaigns(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "campaigns")


@require_permission("seo_view")
def seo(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "seo")


@require_permission("paid_ads_view")
def paid_ads(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "paid_ads")


@require_permission("social_view")
def social(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "social")


@require_permission("email_marketing_view")
def email_marketing(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "email_marketing")


@require_permission("analytics_view")
def analytics(request: HttpRequest) -> HttpResponse:
    if not request.operating.analytics_enabled and not request.user.is_super_admin:
        raise Http404("Analytics are disabled by the website owner.")
    return _placeholder(request, "analytics")


@require_permission("media_view")
def media(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "media")


@require_permission("integrations_view")
def integrations(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "integrations")


@require_permission("audit_view")
def audit(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "audit")


@require_permission("settings_view")
def settings(request: HttpRequest) -> HttpResponse:
    return _placeholder(request, "settings")
