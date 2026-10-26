"""Organization views.

Thin: authorise, call a selector or service, render. Two rules run
through all of them.

**The organization is never taken from the request alone.** A client's
organization comes from `request.organization`, resolved from their
memberships; a staff view takes a slug from the URL and resolves it
through `selectors.get_organization`, which only returns what that actor
may see. A slug that belongs to someone else produces a 404, not a 403 —
confirming that an organization exists is itself information a competitor
should not get.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.organizations import selectors, services
from apps.organizations.forms import (
    AddMemberForm,
    MemberRoleForm,
    OrganizationProfileForm,
    OrganizationSetupForm,
)
from apps.organizations.middleware import SESSION_KEY, has_organization
from apps.organizations.models import MemberRole, OrganizationMember

logger = logging.getLogger(__name__)
User = get_user_model()


def _require_current_organization(request: HttpRequest):  # noqa: ANN202
    """The session's organization, or 404.

    Truthiness, not `is None`: `request.organization` is a lazy proxy, and
    one wrapping None is still an object. See the middleware's docstring.
    """
    if not has_organization(request):
        raise Http404
    return request.organization


@login_required
@require_http_methods(["GET", "POST"])
def setup(request: HttpRequest) -> HttpResponse:
    """Onboarding for a client who has no organization yet.

    Reached by someone who registered without giving a company name, or
    whose account was created by staff. Anyone who already belongs
    somewhere is sent on, so this cannot be used to spawn extra
    organizations.
    """
    if not request.user.is_client:
        raise Http404

    if not selectors.user_needs_onboarding(request.user):
        return redirect("organizations:overview")

    if request.method == "POST":
        form = OrganizationSetupForm(request.POST)
        if form.is_valid():
            organization = services.create_organization(
                owner=request.user,
                actor=request.user,
                status="active",
                **form.cleaned_data,
            )
            messages.success(
                request,
                _("%(name)s is set up. Welcome.") % {"name": organization.label},
            )
            return redirect("organizations:overview")
    else:
        form = OrganizationSetupForm()

    return render(request, "organizations/setup.html", {"form": form})


@login_required
def overview(request: HttpRequest) -> HttpResponse:
    """The client's own organization."""
    if selectors.user_needs_onboarding(request.user):
        return redirect("organizations:setup")

    organization = _require_current_organization(request)

    from apps.analytics.selectors import client_reports
    from apps.approvals import selectors as approval_selectors
    from apps.leads import selectors as quote_selectors
    from apps.notifications import selectors as notification_selectors
    from apps.subscriptions import selectors as service_selectors
    from apps.subscriptions.guards import entitlements
    from apps.subscriptions.invoices import for_client as client_invoices

    pending_approvals = approval_selectors.pending_for(request.user, organization)
    quotes = list(
        quote_selectors.quotes_for_client(request.user).filter(
            Q(organization=organization) | Q(organization__isnull=True)
        )
    )
    subscriptions = list(
        service_selectors.subscriptions_for_client(request.user).filter(organization=organization)
    )
    active = [s for s in subscriptions if s.is_delivering]

    # Recent activity across the client's own services, newest first.
    # Only entries marked for them — the filtering lives in the
    # subscriptions selector so a template cannot forget it.
    activity = []
    for subscription in active[:6]:
        for event in service_selectors.client_visible_events(subscription):
            activity.append((subscription, event))
    activity.sort(key=lambda pair: pair[1].created_at, reverse=True)

    return render(
        request,
        "organizations/overview.html",
        {
            "organization": organization,
            "members": selectors.members_of(request.user, organization),
            "membership": selectors.membership_for(request.user, organization),
            "portal_key": "overview",
            "latest_reports": client_reports(request.user, organization, request.user)[:3],
            "latest_invoices": client_invoices(request.user, organization, request.user)[:3],
            # --- what is running ------------------------------------------
            "active_services": active[:4],
            "active_service_count": len(active),
            "has_any_service": bool(active),
            "entitlements": [m for m in entitlements(request.user) if m.access == "service"],
            # --- what needs them ------------------------------------------
            "pending_approval_count": pending_approvals.count(),
            "pending_approvals": pending_approvals[:5],
            "quotes_awaiting_decision": [q for q in quotes if q.status == "proposal_ready"],
            "unread_messages": notification_selectors.unread_count(request.user),
            # --- what has happened ----------------------------------------
            "recent_activity": activity[:6],
            # --- still open -----------------------------------------------
            "open_quotes": [q for q in quotes if q.is_open][:3],
            "open_quote_count": sum(q.is_open for q in quotes),
            "quotes_needing_reply": [q for q in quotes if q.status == "clarification_required"],
            "quote_count": len(quotes),
            # Modules with nothing behind them yet, named honestly rather
            # than shown as empty panels pretending to hold data.
            "pending_services": [s for s in subscriptions if s.is_open and not s.is_delivering][:3],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request: HttpRequest) -> HttpResponse:
    """Edit the company's details. Owners and admins only."""
    organization = _require_current_organization(request)

    if request.method == "POST":
        form = OrganizationProfileForm.for_organization(organization, data=request.POST)
        if form.is_valid():
            try:
                services.update_organization(
                    organization=organization,
                    actor=request.user,
                    **form.cleaned_data,
                )
            except PermissionDenied:
                # Rendered as a 403 rather than a form error: this is not
                # something the visitor can correct by editing a field.
                raise
            messages.success(request, _("Your organization details have been saved."))
            return redirect("organizations:settings")
    else:
        form = OrganizationProfileForm.for_organization(organization)

    return render(
        request,
        "organizations/settings.html",
        {
            "organization": organization,
            "portal_key": "settings",
            "form": form,
            "can_manage": selectors.membership_for(request.user, organization) is not None
            and selectors.membership_for(request.user, organization).can_manage,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def members(request: HttpRequest) -> HttpResponse:
    """The people in the organization, and the controls to manage them."""
    organization = _require_current_organization(request)
    membership = selectors.membership_for(request.user, organization)
    can_manage = bool(membership and membership.can_manage)

    form = AddMemberForm()

    if request.method == "POST":
        if not can_manage:
            raise PermissionDenied("You may not manage this organization's members.")

        form = AddMemberForm(request.POST)
        if form.is_valid():
            user = User.objects.filter(email=form.cleaned_data["email"]).first()
            if user is None:
                form.add_error(
                    "email",
                    _(
                        "No account exists for that email yet. Ask them to register "
                        "first, then add them here."
                    ),
                )
            else:
                try:
                    services.add_member(
                        organization=organization,
                        user=user,
                        role=form.cleaned_data["role"],
                        job_title=form.cleaned_data["job_title"],
                        actor=request.user,
                    )
                except ValidationError as exc:
                    form.add_error(None, exc.messages[0])
                else:
                    messages.success(
                        request, _("%(email)s has been added.") % {"email": user.email}
                    )
                    return redirect("organizations:members")

    return render(
        request,
        "organizations/members.html",
        {
            "organization": organization,
            "portal_key": "people",
            "members": selectors.members_of(request.user, organization),
            "membership": membership,
            "can_manage": can_manage,
            "form": form,
            "columns": [
                {"label": "Name"},
                {"label": "Role"},
                {"label": "Status"},
                {"label": "", "align": "right", "sr_label": "Actions"},
            ],
            "role_choices": MemberRole.choices,
        },
    )


@login_required
@require_http_methods(["POST"])
def change_member_role(request: HttpRequest, member_id: int) -> HttpResponse:
    """Change one person's role.

    The membership is fetched through the scoped queryset, so an id from
    another organization is simply not found.
    """
    membership = get_object_or_404(
        OrganizationMember.objects.visible_to(request.user), pk=member_id
    )

    form = MemberRoleForm(request.POST)
    if form.is_valid():
        try:
            services.change_member_role(
                membership=membership,
                new_role=form.cleaned_data["role"],
                actor=request.user,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Role updated."))

    return redirect("organizations:members")


@login_required
@require_http_methods(["POST"])
def remove_member(request: HttpRequest, member_id: int) -> HttpResponse:
    membership = get_object_or_404(
        OrganizationMember.objects.visible_to(request.user), pk=member_id
    )

    try:
        services.remove_member(membership=membership, actor=request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(
            request, _("%(email)s has been removed.") % {"email": membership.user.email}
        )

    return redirect("organizations:members")


@login_required
@require_http_methods(["POST"])
def switch(request: HttpRequest) -> HttpResponse:
    """Change which organization the session is working in.

    Only organizations the user actually belongs to are accepted; a
    posted id for anything else is ignored rather than honoured.
    """
    requested = request.POST.get("organization")
    target = (
        selectors.organizations_for_user(request.user).filter(pk=requested).first()
        if requested
        else None
    )

    if target is None:
        raise Http404

    request.session[SESSION_KEY] = target.pk
    return redirect("organizations:overview")
