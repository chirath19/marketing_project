"""Staff administration: accounts, roles and client assignments."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.permissions import access
from apps.permissions.guards import require_permission
from apps.staff import selectors, services
from apps.staff.forms import (
    ClientAssignmentForm,
    OverrideForm,
    RoleAssignmentForm,
    StaffAccountForm,
    StaffProfileForm,
)
from apps.staff.models import StaffClientAssignment, StaffProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Staff administration
# ---------------------------------------------------------------------------


@require_permission("staff_view")
def staff_list(request: HttpRequest) -> HttpResponse:
    return render(request, "staff/list.html", {
        "page_title": "Staff",
        "page_subtitle": "Who works here, what they can do and whose work they do it to.",
        "nav_key": "staff",
        "staff_members": selectors.visible_staff(request.user),
        "columns": [
            {"label": "Name"}, {"label": "Roles"},
            {"label": "Clients", "align": "right"}, {"label": "Status"},
            {"label": "", "align": "right", "sr_label": "Actions"},
        ],
    })


@require_permission("staff_manage")
@require_http_methods(["GET", "POST"])
def staff_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = StaffAccountForm(request.POST, actor=request.user)
        if form.is_valid():
            data = form.cleaned_data
            try:
                profile = services.create_staff_account(
                    email=data["email"], full_name=data["full_name"],
                    password=data["password"], job_title=data["job_title"],
                    department=data["department"], roles=list(data["roles"]),
                    has_all_client_access=data.get("has_all_client_access", False),
                    account_type=data.get("account_type") or "staff",
                    django_admin_access=data.get("django_admin_access", False),
                    actor=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            except services.StaffError as exc:
                form.add_error("email", str(exc))
            except PermissionDenied:
                raise
            else:
                messages.success(request, _("%(email)s can now sign in.") % {
                    "email": profile.user.email})
                return redirect("staff:detail", pk=profile.pk)
    else:
        form = StaffAccountForm(actor=request.user)

    return render(request, "staff/create.html", {
        "page_title": "Add a staff account",
        "page_subtitle": "They can sign in as soon as you save.",
        "nav_key": "staff",
        "breadcrumbs": [{"label": "Staff", "href": "/staff/"}],
        "form": form,
    })


def _staff_profile(request: HttpRequest, pk: int, **_kwargs):  # noqa: ANN202
    return get_object_or_404(StaffProfile.objects.select_related("user"), pk=pk)


@require_permission("staff_view", lookup=_staff_profile)
def staff_detail(request: HttpRequest, pk: int) -> HttpResponse:
    profile = request.authorised_object

    return render(request, "staff/detail.html", {
        "page_title": profile.user.get_full_name(),
        "page_subtitle": profile.user.email,
        "nav_key": "staff",
        "breadcrumbs": [{"label": "Staff", "href": "/staff/"}],
        "profile": profile,
        "assignments": selectors.assignments_for(profile),
        "permissions": sorted(access.permission_codenames_for(profile.user)),
        "override_form": OverrideForm(),
        "overrides": profile.user.permission_overrides.select_related("permission"),
        "profile_form": StaffProfileForm(initial={
            "full_name": profile.user.full_name, "email": profile.user.email,
            "job_title": profile.job_title, "department": profile.department,
            "notes": profile.notes,
        }),
        "role_form": RoleAssignmentForm(initial={"roles": profile.roles.all()}),
        "assignment_form": ClientAssignmentForm(),
        "can_manage": request.user.has_perm("permissions.staff_manage"),
        "can_assign_roles": request.user.has_perm("permissions.staff_assign"),
        "can_assign_clients": request.user.has_perm("permissions.organizations_assign"),
    })


@require_permission("staff_edit", lookup=_staff_profile)
@require_http_methods(["POST"])
def staff_update(request: HttpRequest, pk: int) -> HttpResponse:
    profile = request.authorised_object
    form = StaffProfileForm(request.POST)

    if form.is_valid():
        try:
            services.update_staff(profile=profile, actor=request.user,
                                  **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, _("Profile updated."))

    return redirect("staff:detail", pk=profile.pk)


@require_permission("staff_assign", lookup=_staff_profile)
@require_http_methods(["POST"])
def staff_set_roles(request: HttpRequest, pk: int) -> HttpResponse:
    profile = request.authorised_object
    form = RoleAssignmentForm(request.POST)

    if form.is_valid():
        services.assign_roles(profile=profile, roles=list(form.cleaned_data["roles"]),
                              actor=request.user)
        messages.success(request, _("Roles updated."))

    return redirect("staff:detail", pk=profile.pk)


@require_permission("staff_manage", lookup=_staff_profile)
@require_http_methods(["POST"])
def staff_set_active(request: HttpRequest, pk: int) -> HttpResponse:
    profile = request.authorised_object
    activate = request.POST.get("active") == "1"

    try:
        if activate:
            services.activate_staff(profile=profile, actor=request.user,
                                    reason="Reactivated from staff administration")
        else:
            services.deactivate_staff(profile=profile, actor=request.user,
                                      reason="Deactivated from staff administration")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, getattr(exc, "messages", [str(exc)])[0])
    else:
        messages.success(request, _("Account updated."))

    return redirect("staff:detail", pk=profile.pk)


# ---------------------------------------------------------------------------
# Client assignments
# ---------------------------------------------------------------------------


@require_permission("organizations_assign", lookup=_staff_profile)
@require_http_methods(["POST"])
def assign_client(request: HttpRequest, pk: int) -> HttpResponse:
    profile = request.authorised_object
    form = ClientAssignmentForm(request.POST)

    if form.is_valid():
        services.assign_to_organization(
            profile=profile, organization=form.cleaned_data["organization"],
            role=form.cleaned_data["role"],
            is_primary=form.cleaned_data["is_primary"], actor=request.user,
        )
        messages.success(request, _("Assigned."))
    else:
        messages.error(request, _("That client could not be assigned."))

    return redirect("staff:detail", pk=profile.pk)


@require_permission("organizations_assign")
@require_http_methods(["POST"])
def end_client_assignment(request: HttpRequest, assignment_id: int) -> HttpResponse:
    assignment = get_object_or_404(
        StaffClientAssignment.objects.select_related("staff"), pk=assignment_id
    )
    services.end_assignment(assignment=assignment, actor=request.user)
    messages.success(request, _("Assignment ended."))
    return redirect("staff:detail", pk=assignment.staff_id)


@require_permission('staff_manage', lookup=_staff_profile)
@require_http_methods(['POST'])
def staff_override(request, pk):
    from apps.permissions.services import clear_override, set_override
    from apps.staff.forms import OverrideForm

    profile = request.authorised_object
    form = OverrideForm(request.POST)
    if form.is_valid():
        try:
            if request.POST.get('action') == 'clear':
                clear_override(actor=request.user, user=profile.user,
                               permission_codename=form.cleaned_data['permission'])
            else:
                set_override(actor=request.user, user=profile.user,
                    permission_codename=form.cleaned_data['permission'],
                    effect=form.cleaned_data['effect'], reason=form.cleaned_data['reason'])
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, 'Permission exception updated.')
    else:
        messages.error(request, 'Choose a permission, effect and reason.')
    return redirect('staff:detail', pk=pk)


@require_permission("staff_delete", lookup=_staff_profile)
@require_http_methods(["POST"])
def staff_remove(request, pk):
    try:
        services.remove_staff_account(actor=request.user, profile=request.authorised_object)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, "Account removed. Historical client records are retained.")
    return redirect("staff:detail", pk=pk)
