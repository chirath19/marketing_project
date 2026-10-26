from django import template

from apps.core.workflow import client_navigation, staff_navigation

register = template.Library()


@register.inclusion_tag("workflow/navigation.html", takes_context=True)
def workflow_navigation(context, staff=False):
    request = context["request"]
    links = (
        staff_navigation(request.user, context.get("nav_key", ""))
        if staff
        else client_navigation(
            request.user, getattr(request, "organization", None), context.get("portal_key", "")
        )
    )
    return {"links": links, "staff": staff, "activity": context.get("activity", {})}


@register.inclusion_tag("workflow/location.html", takes_context=True)
def workflow_location(context, staff=False):
    request = context["request"]
    current = context.get("nav_key" if staff else "portal_key", "")
    links = (
        staff_navigation(request.user, current)
        if staff
        else client_navigation(request.user, getattr(request, "organization", None), current)
    )
    parent = next((link for link in links if link["active"]), None)
    return {
        "parent": parent,
        "show": parent and parent["href"] != request.path,
        "staff": staff,
        "current": current,
        "features": context.get("features", {}),
        "title": context.get("desk_heading") or context.get("page_title") or "Details",
        "breadcrumbs": [
            crumb
            for crumb in context.get("breadcrumbs", [])
            if parent and crumb.get("href") != parent["href"]
        ],
    }


@register.inclusion_tag("workflow/quote_journey.html")
def quote_journey(quote):
    stages = {
        "new": 0,
        "reviewing": 1,
        "clarification_required": 1,
        "proposal_ready": 2,
        "accepted": 3,
    }
    explanations = {
        "new": "Your request has arrived. Your team will review it and contact you here.",
        "reviewing": (
            "Your team is preparing the scope and price. You can discuss the details below."
        ),
        "clarification_required": (
            "Your team needs more information. Read their message and reply below."
        ),
        "proposal_ready": (
            "Review the scope and price, then accept or decline this quotation below."
        ),
        "accepted": (
            "Your quotation is accepted. Follow the linked "
            "project for its start date, progress and payments."
        ),
        "declined": (
            "This quotation was declined. Contact your team "
            "if you would like to discuss another approach."
        ),
        "closed": (
            "This request is closed. Its conversation and quotation remain here for your records."
        ),
    }
    current = stages.get(quote.status)
    return {
        "explanation": explanations.get(quote.status, ""),
        "current": current,
        "steps": [
            {
                "label": label,
                "current": index == current,
                "done": current is not None and index < current,
            }
            for index, label in enumerate(
                ["Request received", "Scope & price", "Your decision", "Accepted"]
            )
        ],
    }
