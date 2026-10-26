"""Shared staff inbox and append-only approval management."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.approvals import forms, policies, selectors, services
from apps.organizations import selectors as organizations
from apps.permissions.guards import require_permission, scope_to_accessible


def _get(request, pk):
    approval = selectors.detail_for(request.user, None, pk)
    if approval is None:
        raise Http404("No such approval.")
    return approval


def _detail(request, approval, *, comment_form=None, cancel_form=None, status=200):
    return render(
        request,
        "approvals/admin/detail.html",
        {
            "approval": approval,
            "page_title": approval.title,
            "nav_key": "approvals",
            "is_staff_workspace": True,
            "can_comment": policies.can_comment(request.user, approval),
            "can_cancel": policies.can_cancel(request.user, approval),
            "comment_form": comment_form or forms.CommentForm(),
            "cancel_form": cancel_form or forms.CancelForm(),
        },
        status=status,
    )


@require_permission("approvals_view")
def inbox(request):
    rows = selectors.requests_for(request.user)
    data = request.GET.copy()
    if "status" not in data:
        data["status"] = "pending"
    form = forms.FilterForm(data)
    if form.is_valid():
        if form.cleaned_data["status"]:
            rows = rows.filter(status=form.cleaned_data["status"])
        if form.cleaned_data["search"]:
            rows = rows.filter(title__icontains=form.cleaned_data["search"])
    else:
        rows = rows.none()
    query = data.copy()
    query.pop("page", None)
    clients = scope_to_accessible(
        organizations.visible_organizations(request.user), request.user, field="id"
    ).order_by("name")
    return render(
        request,
        "approvals/admin/inbox.html",
        {
            "page_title": "Client approvals",
            "nav_key": "approvals",
            "is_staff_workspace": True,
            "filter_form": form,
            "page_obj": Paginator(rows, 25).get_page(request.GET.get("page")),
            "querystring": query.urlencode(),
            "pending_count": selectors.pending_for(request.user).count(),
            "organizations": clients,
            "can_create": request.user.has_perm("permissions.approvals_create"),
        },
        status=200 if form.is_valid() else 400,
    )


@require_permission("approvals_create")
@require_http_methods(["GET", "POST"])
def create(request, slug):
    organization = organizations.get_organization(request.user, slug)
    if not organization or not policies.can_create(request.user, organization):
        raise Http404("No such workspace.")
    form = forms.RequestForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
        organization=organization,
    )
    if request.method == "POST" and form.is_valid():
        try:
            approval = services.create_request(
                actor=request.user, organization=organization, **form.cleaned_data
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Client approval requested.")
            return redirect("staff:approval_detail", pk=approval.pk)
    return render(
        request,
        "approvals/admin/form.html",
        {
            "organization": organization,
            "form": form,
            "nav_key": "approvals",
            "page_title": "Request client approval",
        },
        status=400 if request.method == "POST" and form.errors else 200,
    )


@require_permission("approvals_view")
def detail(request, pk):
    return _detail(request, _get(request, pk))


@require_permission("approvals_view")
@require_POST
def comment(request, pk):
    approval = _get(request, pk)
    form = forms.CommentForm(request.POST)
    if form.is_valid():
        services.add_comment(
            actor=request.user,
            organization=approval.organization,
            request=approval,
            **form.cleaned_data,
        )
        messages.success(request, "Comment added.")
        return redirect("staff:approval_detail", pk=pk)
    return _detail(request, approval, comment_form=form, status=400)


@require_permission("approvals_approve")
@require_POST
def cancel(request, pk):
    approval = _get(request, pk)
    form = forms.CancelForm(request.POST)
    if form.is_valid():
        try:
            services.cancel(
                actor=request.user,
                organization=approval.organization,
                request=approval,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Approval request cancelled.")
            return redirect("staff:approval_detail", pk=pk)
    return _detail(request, approval, cancel_form=form, status=400)
