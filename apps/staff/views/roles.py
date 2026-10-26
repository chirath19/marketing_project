"""Role configuration."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.permissions import selectors as permission_selectors
from apps.permissions.guards import require_permission

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@require_permission("roles_view")
def role_list(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "staff/roles.html",
        {
            "page_title": "Roles and permissions",
            "page_subtitle": "Bundles of permissions assigned to staff.",
            "nav_key": "roles",
            "roles": permission_selectors.visible_roles(request.user),
            "columns": [
                {"label": "Role"},
                {"label": "Permissions", "align": "right"},
                {"label": "Description"},
            ],
        },
    )


def _role(request: HttpRequest, pk: int, **_kwargs):  # noqa: ANN202
    role = permission_selectors.get_role(request.user, pk)
    if role is None:
        raise Http404
    return role


@require_permission("roles_view", lookup=_role)
def role_detail(request: HttpRequest, pk: int) -> HttpResponse:
    role = request.authorised_object

    return render(
        request,
        "staff/role_detail.html",
        {
            "page_title": role.name,
            "page_subtitle": role.description,
            "nav_key": "roles",
            "breadcrumbs": [{"label": "Roles", "href": "/staff/roles/"}],
            "role": role,
            "modules": permission_selectors.role_permission_matrix(role, request.user),
            "can_manage": request.user.has_perm("permissions.roles_manage"),
        },
    )


@require_permission("roles_manage", lookup=_role)
@require_http_methods(["POST"])
def role_set_permissions(request: HttpRequest, pk: int) -> HttpResponse:
    """Replace a role's permissions with the boxes that were ticked."""
    from apps.permissions import services as permission_services

    role = request.authorised_object
    codenames = request.POST.getlist("permissions")

    try:
        permission_services.set_role_permissions(role=role, codenames=codenames, actor=request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, _("Permissions updated."))

    return redirect("staff:role_detail", pk=role.pk)


@require_permission("roles_manage")
@require_http_methods(["GET", "POST"])
def role_create(request):
    from apps.permissions.services import create_role
    from apps.staff.forms import RoleForm

    form = RoleForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            role = create_role(actor=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("staff:role_detail", pk=role.pk)
    return render(
        request,
        "staff/role_form.html",
        {"form": form, "nav_key": "roles", "page_title": "Create a role"},
    )


@require_permission("roles_manage", lookup=_role)
@require_http_methods(["GET", "POST"])
def role_edit(request, pk):
    from apps.permissions.services import update_role
    from apps.staff.forms import RoleForm

    role = request.authorised_object
    form = RoleForm(
        request.POST if request.method == "POST" else None,
        initial={"name": role.name, "description": role.description},
    )
    if request.method == "POST" and form.is_valid():
        try:
            update_role(actor=request.user, role=role, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            return redirect("staff:role_detail", pk=role.pk)
    return render(
        request,
        "staff/role_form.html",
        {"form": form, "nav_key": "roles", "page_title": "Edit role"},
    )


@require_permission("roles_manage", lookup=_role)
@require_http_methods(["POST"])
def role_delete(request, pk):
    from apps.permissions.services import delete_role

    try:
        delete_role(actor=request.user, role=request.authorised_object)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("staff:role_detail", pk=pk)
    return redirect("staff:roles")
