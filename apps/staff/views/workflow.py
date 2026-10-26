"""Workflow entry points; existing domain routes remain independently guarded."""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render

from apps.core.workflow import staff_areas
from apps.messaging import selectors as messaging
from apps.messaging.policies import may_access
from apps.permissions.guards import require_staff_member


@require_staff_member
def workspace(request, area):
    areas = staff_areas(request.user)
    if area == "payments":
        from apps.core.features import require
        from apps.permissions.access import has_permission

        require("payments", request.user)
        if not has_permission(request.user, "permissions.subscriptions_view"):
            raise PermissionDenied
        section = {
            "key": area,
            "label": "Payments",
            "items": [],
            "description": "Choose a client to manage invoices, payments and receipts.",
        }
    elif area in areas:
        section = areas[area]
    else:
        raise Http404
    context = {
        "page_title": section["label"],
        "page_subtitle": section["description"],
        "nav_key": area,
        "section": section,
    }
    if area == "requests":
        from apps.leads.selectors import quote_requests

        context["quotes"] = quote_requests(request.user)[:8]
    elif area == "projects":
        from apps.subscriptions.selectors import visible_subscriptions

        context["projects"] = visible_subscriptions(request.user).order_by("-updated_at")[:8]
        context["report_recipients"] = [
            member
            for member in messaging.recipients(request.user)
            if may_access(request.user, member.organization, member.user, "analytics_view")
        ]
    elif area == "payments":
        context["recipients"] = [
            member
            for member in messaging.recipients(request.user)
            if may_access(request.user, member.organization, member.user, "subscriptions_view")
        ]
    return render(request, "workflow/staff_hub.html", context)
