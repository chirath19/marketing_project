"""The dashboard home and global search.

The home page shows counts drawn from real tables and nothing else. Where
a figure would need a module that does not exist yet, the page says so
rather than inventing a number — a dashboard that lies during development
teaches everyone to distrust it later.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.accounts import selectors as account_selectors
from apps.organizations import selectors as organization_selectors
from apps.permissions import access
from apps.permissions.catalogue import APP_LABEL
from apps.permissions.guards import require_staff_member, scope_to_accessible
from apps.staff import selectors as staff_selectors


def _can(user, codename: str) -> bool:  # noqa: ANN001
    return access.has_permission(user, f"{APP_LABEL}.{codename}")


@require_staff_member
def dashboard(request: HttpRequest) -> HttpResponse:
    """What needs attention, from data that actually exists."""
    user = request.user
    stats = []

    if _can(user, "organizations_view"):
        clients = scope_to_accessible(
            organization_selectors.visible_organizations(user),
            user,
            field="id",
        )
        stats.append(
            {
                "label": "Clients",
                "value": clients.count(),
                "caption": "Assigned to you"
                if access.accessible_organization_ids(user) is not None
                else "Across the agency",
                "href": "staff:clients",
            }
        )
        pending = scope_to_accessible(
            organization_selectors.pending_onboarding(user),
            user,
            field="id",
        ).count()
        if pending:
            stats.append(
                {
                    "label": "Awaiting onboarding",
                    "value": pending,
                    "caption": "Client organizations not yet active",
                    "href": "staff:clients",
                }
            )

    if _can(user, "staff_view"):
        stats.append(
            {
                "label": "Staff",
                "value": staff_selectors.visible_staff(user).count(),
                "caption": "Accounts on the platform",
                "href": "staff:list",
            }
        )

    if _can(user, "leads_view"):
        from apps.leads import selectors as lead_selectors

        counts = lead_selectors.inbox_counts(user)
        stats.extend(
            [
                {
                    "label": "Unread enquiries",
                    "value": counts["unread"],
                    "caption": "Waiting to be opened",
                    "href": "staff:module_inbox",
                },
                {
                    "label": "New leads",
                    "value": counts["new_leads"],
                    "caption": "Nobody has acted on them yet",
                    "href": "staff:module_leads",
                },
                {
                    "label": "Unassigned leads",
                    "value": counts["unassigned"],
                    "caption": "Open, with no owner",
                    "href": "staff:module_leads",
                },
            ]
        )

    if _can(user, "quotes_view"):
        from apps.leads import selectors as lead_selectors

        stats.append(
            {
                "label": "Open quotes",
                "value": lead_selectors.open_quote_request_count(user),
                "caption": "Still waiting on somebody",
                "href": "staff:module_quotes",
            }
        )
        stats.append(
            {
                "label": "Unread quote requests",
                "value": lead_selectors.open_quote_count(user),
                "caption": "Nobody has opened them yet",
                "href": "staff:quote_inbox",
            }
        )

    if _can(user, "campaigns_view"):
        from apps.campaigns import selectors as campaign_selectors

        stats.append(
            {
                "label": "Live campaigns",
                "value": campaign_selectors.running_count(user),
                "caption": "Running across every service",
                "href": "staff:module_campaigns",
            }
        )
        late = campaign_selectors.overdue(user).count()
        if late:
            stats.append(
                {
                    "label": "Past their end date",
                    "value": late,
                    "caption": "Still open, but the period has gone by",
                    "href": "staff:module_campaigns",
                }
            )

    approval_queue = []
    if _can(user, "approvals_view"):
        from apps.approvals import selectors as approval_selectors

        pending_approvals = approval_selectors.pending_for(user)
        stats.append(
            {
                "label": "Pending client approvals",
                "value": pending_approvals.count(),
                "caption": "Waiting for a client decision",
                "href": "staff:module_approvals",
            }
        )
        approval_queue = pending_approvals[:5]

    if _can(user, "subscriptions_view"):
        from apps.subscriptions import selectors as subscription_selectors

        stats.append(
            {
                "label": "Active services",
                "value": subscription_selectors.active_subscription_count(user),
                "caption": "Being delivered right now",
                "href": "staff:module_subscriptions",
            }
        )
        ending = subscription_selectors.expiring_soon(user).count()
        if ending:
            stats.append(
                {
                    "label": "Ending soon",
                    "value": ending,
                    "caption": "Within 30 days, and still open",
                    "href": "staff:module_subscriptions",
                }
            )

    if _can(user, "catalog_view"):
        from apps.catalog import selectors as catalog_selectors

        stats.append(
            {
                "label": "Live services",
                "value": catalog_selectors.live_services().count(),
                "caption": "Published in the public catalogue",
                "href": "staff:module_services",
            }
        )

    if user.is_super_admin or user.is_system_owner:
        waiting = account_selectors.pending_approval_count(user)
        stats.append(
            {
                "label": "Registrations to approve",
                "value": waiting,
                "caption": "Clients who signed up and are waiting",
                "href": "staff:registrations",
            }
        )

    return render(
        request,
        "admin/dashboard.html",
        {
            "page_title": "Dashboard",
            "page_subtitle": "What needs your attention.",
            "nav_key": "dashboard",
            "stats": stats,
            "workflow_stats": [
                s
                for s in stats
                if s["label"] in {"Clients", "Open quotes", "Active services", "Unread enquiries"}
            ],
            "attention_stats": [
                s
                for s in stats
                if s["value"]
                and s["label"]
                in {
                    "Unread quote requests",
                    "Unread enquiries",
                    "Ending soon",
                    "Registrations to approve",
                    "Past their end date",
                }
            ],
            "pending_approvals": approval_queue,
            "assignments": staff_selectors.assigned_organizations(user)[:6]
            if _can(user, "organizations_view")
            else [],
        },
    )


@require_staff_member
def search(request: HttpRequest) -> HttpResponse:
    """Search across what exists, scoped to what this actor may see.

    Results come from the same selectors the list pages use, so search can
    never surface a record a page would have hidden.
    """
    query = (request.GET.get("q") or "").strip()
    user = request.user

    clients = []
    staff_results = []

    if query:
        if _can(user, "organizations_view"):
            clients = (
                scope_to_accessible(
                    organization_selectors.visible_organizations(user),
                    user,
                    field="id",
                )
                .filter(name__icontains=query)
                .order_by("name")[:20]
            )

        if _can(user, "staff_view"):
            staff_results = staff_selectors.visible_staff(user).filter(
                user__email__icontains=query
            )[:20]

    return render(
        request,
        "admin/search.html",
        {
            "page_title": "Search",
            "page_subtitle": f"Results for “{query}”" if query else "",
            "nav_key": "",
            "query": query,
            "clients": clients,
            "staff_results": staff_results,
            "has_results": bool(clients) or bool(staff_results),
            "breadcrumbs": [{"label": "Dashboard", "href": "/staff/dashboard/"}],
        },
    )
