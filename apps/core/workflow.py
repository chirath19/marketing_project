"""Workflow presentation. Domain registries remain the source of access rights."""

from django.urls import reverse

STAFF_AREAS = {
    "requests": (
        "Requests & quotes",
        "Review enquiries, prepare a quotation and agree the next step.",
        ("quotes", "inbox", "leads", "service_requests"),
    ),
    "projects": (
        "Projects & services",
        "Manage agreed work, share progress and request client decisions.",
        ("subscriptions", "approvals", "campaigns", "seo", "paid_ads", "social", "email_marketing"),
    ),
    "website": (
        "Website & content",
        "Manage what visitors see, including services, pages and articles.",
        ("cms", "services", "blog", "media"),
    ),
    "administration": (
        "Team & administration",
        "Manage your team, access and advanced platform settings.",
        ("staff", "roles", "settings", "integrations", "analytics", "audit"),
    ),
}
LABELS = {
    "quotes": "Quotations",
    "inbox": "New enquiries",
    "leads": "Enquiry follow-up",
    "service_requests": "Renewals & extra work",
    "subscriptions": "All projects & services",
    "approvals": "Work awaiting client review",
    "campaigns": "Campaign work",
    "services": "Service catalogue",
    "staff": "Team members",
    "cms": "Pages & website settings",
}


def staff_areas(user):
    from apps.staff.navigation import visible_navigation

    allowed = {item.key: item for group in visible_navigation(user) for item in group["items"]}
    from apps.core.features import visible
    from apps.permissions.access import has_permission

    areas = {}
    for key, (label, description, keys) in STAFF_AREAS.items():
        items = [
            {
                "key": item.key,
                "label": LABELS.get(item.key, item.label),
                "href": reverse(item.url_name),
                "description": item.description,
                "built": item.built,
            }
            for k in keys
            if (item := allowed.get(k))
        ]
        if items:
            areas[key] = {
                "key": key,
                "label": label,
                "description": description,
                "href": reverse("staff:workflow", args=[key]),
                "items": items,
            }
    if (
        visible("reports", user)
        and has_permission(user, "permissions.analytics_view")
        and "projects" not in areas
    ):
        areas["projects"] = {
            "key": "projects",
            "label": "Projects & services",
            "description": "Share progress updates with your clients.",
            "href": reverse("staff:workflow", args=["projects"]),
            "items": [],
        }
    return areas


def staff_navigation(user, current=""):
    from apps.core.features import visible
    from apps.permissions.access import has_permission

    areas = staff_areas(user)
    parent = next((key for key, (_, _, keys) in STAFF_AREAS.items() if current in keys), current)
    links = [{"key": "dashboard", "label": "Dashboard", "href": reverse("staff:dashboard")}]
    if has_permission(user, "permissions.organizations_view"):
        links.append({"key": "clients", "label": "Clients", "href": reverse("staff:clients")})
    links.extend(areas[k] for k in ("requests", "projects") if k in areas)
    if visible("messages", user) and has_permission(user, "permissions.messaging_view"):
        links.append(
            {
                "key": "messages",
                "label": "Messages",
                "href": reverse("staff:module_messages"),
                "badge": "messages",
            }
        )
    if visible("payments", user) and has_permission(user, "permissions.subscriptions_view"):
        links.append(
            {
                "key": "payments",
                "label": "Payments",
                "href": reverse("staff:workflow", args=["payments"]),
            }
        )
    links.extend(areas[k] for k in ("website", "administration") if k in areas)
    for item in links:
        item["active"] = item["key"] == parent
        if item["key"] == "requests":
            item["badge"] = (
                "enquiries" if has_permission(user, "permissions.leads_view") else "quotes"
            )
    return links


def client_navigation(user, organization, current=""):
    from apps.subscriptions.guards import entitlement_keys

    keys = entitlement_keys(user, organization=organization)
    parent = {
        "quotes": "requests",
        "service_requests": "requests",
        "services": "projects",
        "reports": "projects",
        "campaigns": "projects",
        "seo": "projects",
        "paid_ads": "projects",
        "social": "projects",
        "email_marketing": "projects",
        "analytics": "projects",
        "strategy": "projects",
        "approvals": "projects",
        "invoices": "payments",
        "receipts": "payments",
        "settings": "account",
        "people": "account",
    }.get(current, current)
    definitions = [
        ("overview", "Overview", "overview", "organizations:overview"),
        ("requests", "Requests & quotes", "quotes", "organizations:quotes"),
        ("projects", "Projects & services", "services", "organizations:services"),
        ("messages", "Messages", "messages", "organizations:client_desk"),
        ("payments", "Payments", "invoices", "organizations:client_invoices"),
        ("account", "Account", "settings", "organizations:settings"),
    ]
    return [
        {
            "key": key,
            "label": label,
            "href": reverse(route),
            "active": key == parent,
            "badge": "messages" if key == "messages" else "",
        }
        for key, label, required, route in definitions
        if required in keys
    ]
