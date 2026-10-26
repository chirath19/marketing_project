"""Client approval inbox scoped to the selected organization and current sharing."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.approvals import forms, policies, selectors, services


def _organization(request):
    organization = request.organization
    if request.user.is_staff_member or not policies.can_open(request.user, organization):
        raise PermissionDenied("This workspace requires active membership and a client service.")
    return organization


def _get(request, pk):
    approval = selectors.detail_for(request.user, _organization(request), pk)
    if approval is None:
        raise Http404("No such approval.")
    return approval


def _detail(request, approval, *, decision_form=None, comment_form=None, status=200):
    return render(
        request,
        "approvals/client/detail.html",
        {
            "organization": approval.organization,
            "approval": approval,
            "page_title": approval.title,
            "portal_key": "approvals",
            "can_respond": policies.can_respond(request.user, approval),
            "can_comment": policies.can_comment(request.user, approval),
            "decision_form": decision_form or forms.DecisionForm(),
            "comment_form": comment_form or forms.CommentForm(),
        },
        status=status,
    )


@login_required
def inbox(request):
    organization = _organization(request)
    rows = selectors.requests_for(request.user, organization)
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
    return render(
        request,
        "approvals/client/inbox.html",
        {
            "organization": organization,
            "page_title": "Approvals",
            "portal_key": "approvals",
            "filter_form": form,
            "page_obj": Paginator(rows, 25).get_page(request.GET.get("page")),
            "querystring": query.urlencode(),
            "pending_count": selectors.pending_for(request.user, organization).count(),
        },
        status=200 if form.is_valid() else 400,
    )


@login_required
def detail(request, pk):
    return _detail(request, _get(request, pk))


@login_required
@require_POST
def decide(request, pk):
    approval = _get(request, pk)
    if not policies.can_respond(request.user, approval):
        raise PermissionDenied("Your membership is read-only.")
    form = forms.DecisionForm(request.POST)
    if form.is_valid():
        try:
            services.decide(
                actor=request.user,
                organization=approval.organization,
                request=approval,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Your decision has been recorded.")
            return redirect("organizations:approval_detail", pk=pk)
    return _detail(request, approval, decision_form=form, status=400)


@login_required
@require_POST
def comment(request, pk):
    approval = _get(request, pk)
    if not policies.can_comment(request.user, approval):
        raise PermissionDenied("Your membership is read-only.")
    form = forms.CommentForm(request.POST)
    if form.is_valid():
        services.add_comment(
            actor=request.user,
            organization=approval.organization,
            request=approval,
            **form.cleaned_data,
        )
        messages.success(request, "Comment added.")
        return redirect("organizations:approval_detail", pk=pk)
    return _detail(request, approval, comment_form=form, status=400)
