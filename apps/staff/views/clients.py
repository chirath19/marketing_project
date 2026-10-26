"""Staff-side client views, downloads and exports.

Each one passes a `lookup` to the guard, so the permission is checked
against the client in question — permission alone is not access.
"""

from __future__ import annotations

import csv
import logging

from django.http import Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.organizations import selectors as organization_selectors
from apps.permissions import access
from apps.permissions.guards import require_permission, scope_to_accessible
from apps.staff import selectors

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Staff-side client views — the object endpoints
# ---------------------------------------------------------------------------


@require_permission("organizations_view")
def client_list(request: HttpRequest) -> HttpResponse:
    """Clients this staff member may see.

    The permission opens the page; `scope_to_accessible` decides which
    rows are on it. A permission check alone cannot filter rows, and a
    list that ignores assignments is a quiet way around every object-level
    check.
    """
    clients = scope_to_accessible(
        organization_selectors.visible_organizations(request.user).order_by("name"),
        request.user,
        field="id",
    )

    # Said accurately for whoever is reading: telling an administrator
    # who can see every client that this is "only the clients you are
    # assigned to" is simply false, and quietly teaches people that the
    # labels on this platform are approximate.
    scoped = access.accessible_organization_ids(request.user) is not None

    return render(
        request,
        "staff/clients.html",
        {
            "page_title": "Clients",
            "page_subtitle": (
                "The client organizations you are assigned to."
                if scoped
                else "Every client organization on the platform."
            ),
            "nav_key": "clients",
            "clients": clients,
            "is_scoped": scoped,
            "columns": [{"label": "Client"}, {"label": "Status"}, {"label": "Reference"}],
        },
    )


def _organization(request: HttpRequest, slug: str, **_kwargs):  # noqa: ANN202
    """Resolve the client the action is about.

    Read through the organizations domain's own selector rather than its
    model, so the two domains stay joined by a contract and not by an
    import. The selector decides what is visible at all; the guard then
    decides whether this actor is assigned to it.
    """
    organization = organization_selectors.get_organization(request.user, slug)
    if organization is None:
        raise Http404
    return organization


@require_permission("organizations_view", lookup=_organization)
def client_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """One client. The object endpoint the brief asks to be protected.

    `lookup` resolves the organization before the check, so a staff member
    with `organizations_view` but no assignment to *this* client is
    refused — permission alone is not access.
    """
    organization = request.authorised_object

    from apps.campaigns import policies as campaign_policies
    from apps.campaigns import selectors as campaign_selectors
    from apps.staff.client_workspace import context_for
    from apps.subscriptions import policies as subscription_policies
    from apps.subscriptions import selectors as subscription_selectors

    client_members = (
        organization_selectors.members_of(request.user, organization)
        .filter(user__user_type="client", status="active")
        .select_related("user")
    )
    workspace = context_for(
        request.user,
        organization,
        client_members,
        request.GET.get("client"),
        request.GET.get("quote_page"),
    )

    return render(
        request,
        "staff/client_detail.html",
        {
            **workspace,
            "page_title": organization.label,
            "page_subtitle": organization.name,
            "nav_key": "clients",
            "breadcrumbs": [{"label": "Clients", "href": "/staff/clients/"}],
            "organization": organization,
            "client_members": client_members,
            "assigned_staff": selectors.staff_for_organization(organization),
            "can_edit": request.user.has_perm("permissions.organizations_edit", organization),
            # What this client is paying for, read through the subscriptions
            # domain's own selector so the tenancy rule is applied once.
            "subscriptions": subscription_selectors.for_organization(request.user, organization),
            "can_add_service": subscription_policies.can_create_subscriptions(
                request.user, organization
            ),
            "campaigns": campaign_selectors.for_organization(request.user, organization)[:6],
            "can_add_campaign": campaign_policies.can_create_campaigns(request.user, organization),
        },
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class _Echo:
    """A file-like object that returns what it is given, for csv.writer."""

    def write(self, value: str) -> str:
        return value


@require_permission("organizations_export")
def export_clients(request: HttpRequest) -> StreamingHttpResponse:
    """CSV of the clients this staff member may see.

    Two guards, both needed. `require_permission` decides whether an
    export may happen at all; `scope_to_accessible` decides what goes in
    the file. An export that skipped the second would hand an unassigned
    specialist the entire client book in one click — the exact failure the
    object-level checks exist to prevent.
    """
    clients = scope_to_accessible(
        organization_selectors.visible_organizations(request.user).order_by("name"),
        request.user,
        field="id",
    ).values_list("name", "slug", "status", "city", "country", "created_at")

    def rows():
        writer = csv.writer(_Echo())
        yield writer.writerow(["Name", "Slug", "Status", "City", "Country", "Created"])
        for row in clients:
            yield writer.writerow(
                [
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5].strftime("%Y-%m-%d") if row[5] else "",
                ]
            )

    stamp = timezone.now().strftime("%Y%m%d")
    response = StreamingHttpResponse(rows(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="clients-{stamp}.csv"'
    logger.info("Client export by %s", request.user.email)
    return response


@require_permission("organizations_export", lookup=_organization)
def export_client(request: HttpRequest, slug: str) -> HttpResponse:
    """A single client's details — a download scoped to one object."""
    organization = request.authorised_object

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{organization.slug}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Field", "Value"])
    for field in ("name", "display_name", "slug", "status", "website", "phone", "city", "country"):
        writer.writerow([field, getattr(organization, field, "")])
    return response


@require_permission("organizations_manage")
def registrations(request):
    from django.core.exceptions import PermissionDenied

    from apps.accounts.selectors import pending_approvals

    if not (request.user.is_super_admin or request.user.is_system_owner):
        raise PermissionDenied
    return render(
        request,
        "staff/registrations.html",
        {
            "page_title": "Client registrations",
            "nav_key": "clients",
            "registrations": pending_approvals(request.user),
        },
    )


@require_permission("organizations_manage")
def approve_registration(request, user_id):
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied, ValidationError
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import redirect

    from apps.accounts.selectors import pending_approvals
    from apps.staff.services import approve_client_registration

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not (request.user.is_super_admin or request.user.is_system_owner):
        raise PermissionDenied
    user = pending_approvals(request.user).filter(pk=user_id).first()
    if not user:
        raise Http404
    try:
        approve_client_registration(actor=request.user, user=user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, "Client account and workspace approved.")
    return redirect("staff:registrations")
