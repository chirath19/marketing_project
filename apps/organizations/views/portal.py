"""The client portal's delivery modules.

One view, not ten. Each module declares what it is and what it will hold
in `apps/core/modules.py`; this renders whichever one the client asked
for, after checking they are entitled to it.

That is the shape the brief asks for — a dashboard whose navigation
depends on what the client has bought — implemented as data rather than
as ten near-identical view functions that would drift apart within a
month.

Campaigns are the first real content to arrive here, and they arrive for
**every** area at once: the combined campaigns page and each service
area's own page are the same query with a different filter. That is the
dividend of one campaign table rather than one per service.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from apps.campaigns.views.client import grouped_for_client
from apps.core.modules import SERVICE, get_module
from apps.subscriptions import selectors as service_selectors
from apps.subscriptions.guards import can_open_module


@login_required
def module_page(request: HttpRequest, key: str) -> HttpResponse:
    """One delivery module.

    The entitlement check is explicit here rather than applied by the
    decorator, because the module being asked for arrives in the URL —
    a decorator can only guard a fixed key. It calls exactly the same
    function the decorator would.
    """
    if key == "approvals":
        from apps.approvals.views.client import inbox
        return inbox(request)
    if key == "email_marketing":
        from apps.email_marketing.views.client import workspace
        return workspace(request)
    if key == "social":
        from apps.social.views.client import workspace
        return workspace(request)
    if key == "paid_ads":
        from apps.paid_ads.views.client import workspace

        return workspace(request)

    module = get_module(key)

    # A module with a page of its own is a 404 here, whatever unlocks it:
    # two addresses for one screen is a trap for whoever maintains it.
    #
    # Keyed on `url_name` and not on `access`, which was once the bug —
    # a module can be available to everybody *and* still have no page of
    # its own, which is exactly what Messages is.
    if module is None or module.url_name:
        raise Http404("No such area.")

    # An unknown key is a 404; a known one the client has not earned is a
    # 403. The difference matters: the first does not exist, the second
    # exists and is not theirs yet, and telling them so is how they know
    # to ask for it.
    if not can_open_module(request.user, key):
        raise PermissionDenied("Your account does not include this area.")

    # Campaigns: everything for the combined page, this area's only for a
    # service module. One query, filtered — not two code paths.
    campaigns = None
    if key == "campaigns":
        campaigns = grouped_for_client(request.user)
    elif module.access == SERVICE:
        campaigns = grouped_for_client(request.user, service_type=key)

    # A service module may contribute a richer page of its own data. SEO
    # is the first; the hook is a plain function so a module can add one
    # without this view growing a branch per area.
    extra = _module_extras(request.user, key)

    # The services that opened this area, so the page can say why the
    # client is looking at it.
    opened_by = [
        subscription
        for subscription in service_selectors.subscriptions_for_client(request.user)
        if subscription.is_delivering
        and (module.access != SERVICE
             or (subscription.workspace_module is not None
                 and subscription.workspace_module.key == key))
    ]

    return render(request, "portal/module.html", {
        "page_title": module.label,
        "module": module,
        "opened_by": opened_by,
        "portal_key": key,
        "campaigns": campaigns,
        **extra,
        # Whether the page has anything real on it yet. Decides between
        # showing work and explaining that there is none.
        "has_content": bool(
            (campaigns and campaigns["total"]) or extra.get("seo")
        ),
    })


#: Service modules that contribute their own data to their portal area.
#: A plain mapping rather than a chain of `if key == ...`, so adding the
#: paid-ads workspace later means adding one line here.
def _module_extras(user, key: str) -> dict:  # noqa: ANN001
    if key == "seo":
        from apps.seo import selectors as seo_selectors

        workspace = seo_selectors.client_workspace(user)
        # Only treated as content when there is something recorded —
        # otherwise the page should say so rather than show empty cards.
        if workspace.get("organization") and seo_selectors.has_any_data(
            workspace["organization"]
        ):
            return {"seo": workspace}

    return {}
