"""A client's own services, inside their workspace.

Mounted under the organizations namespace because that is where a client
looks for them, and owned by this domain because that is where the data
lives — the same arrangement the staff dashboard uses for the Inbox and
the quote pipeline.

There is no permission to require: a client holds none. Every view here
resolves the record through `selectors.client_subscription`, which
applies the ownership rule to the row itself and returns None otherwise.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.subscriptions import selectors
from apps.subscriptions.models import DELIVERING_STATUSES, OPEN_STATUSES


@login_required
def service_list(request: HttpRequest) -> HttpResponse:
    """Everything this client has bought, past and present."""
    subscriptions = list(
        selectors.subscriptions_for_client(request.user).filter(organization=request.organization)
    )

    return render(
        request,
        "subscriptions/client/list.html",
        {
            "page_title": "Projects & services",
            "portal_key": "services",
            "active": [s for s in subscriptions if s.status in DELIVERING_STATUSES],
            "other_open": [
                s
                for s in subscriptions
                if s.status in OPEN_STATUSES and s.status not in DELIVERING_STATUSES
            ],
            "finished": [s for s in subscriptions if not s.is_open],
            "modules": selectors.unlocked_modules(request.user),
            "project_reviews": _project_reviews(request),
            "can_review_work": _can_review_work(request),
            "shared_work_modules": _shared_work_modules(request),
        },
    )


@login_required
def service_detail(request: HttpRequest, pk: int) -> HttpResponse:
    subscription = selectors.client_subscription(request.user, pk)
    if subscription is None or subscription.organization_id != getattr(
        request.organization, "pk", None
    ):
        # 404, not 403. Confirming another client's service exists is
        # itself information they should not get.
        raise Http404("No such service.")

    from apps.campaigns import selectors as campaign_selectors
    from apps.subscriptions.workspace import client_project

    campaigns = list(
        campaign_selectors.campaigns_for_client(request.user, subscription=subscription)
    )

    return render(
        request,
        "subscriptions/client/detail.html",
        {
            **client_project(request.user, subscription),
            "page_title": subscription.name,
            "portal_key": "services",
            "subscription": subscription,
            # Filtered in the selector, not here: a condition forgotten in
            # one template is how an internal note reaches a client.
            "events": selectors.client_visible_events(subscription),
            "module": subscription.workspace_module,
            "campaigns": campaigns,
            # `is_running` rather than importing `RUNNING_STATUSES` — a view
            # reads another domain's model through its own property, never
            # its internals, the same rule `tests/test_architecture.py`
            # checks for every presentation module.
            "live_campaign_count": sum(1 for c in campaigns if c.is_running),
        },
    )


def _project_reviews(request):
    from apps.approvals.selectors import pending_for

    return pending_for(request.user, request.organization)


def _can_review_work(request):
    from apps.subscriptions.guards import can_open_module

    return can_open_module(request.user, "approvals", organization=request.organization)


def _shared_work_modules(request):
    from apps.subscriptions.guards import entitlements

    return [
        module
        for module in entitlements(request.user, organization=request.organization)
        if module.key in {"campaigns", "analytics", "strategy"}
    ]
