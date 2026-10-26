"""Clients see explicitly shared work in their selected, subscribed organization."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.email_marketing import forms, policies, selectors, services


def _organization(request):
    organization = request.organization
    if request.user.is_staff_member or not policies.can_read(request.user, organization):
        raise PermissionDenied(
            "This workspace requires an active Email Marketing service and membership."
        )
    return organization


def _get(queryset, pk):
    record = queryset.filter(pk=pk).first()
    if record is None:
        raise Http404("No such email marketing work.")
    return record


@login_required
def workspace(request):
    organization = _organization(request)
    form = forms.FilterForm(request.GET, actor=request.user, organization=organization)
    context = {
        "organization": organization,
        "portal_key": "email_marketing",
        "page_title": "Email Marketing",
        "filter_form": form,
        "campaigns": selectors.campaigns_for(request.user, organization),
    }
    if form.is_valid():
        context.update(selectors.workspace(request.user, organization, form.cleaned_data))
        context["work_items"] = Paginator(context["work_items"], 25).get_page(
            request.GET.get("page")
        )
        context["results"] = Paginator(context["results"], 31).get_page(
            request.GET.get("results_page")
        )
    query = request.GET.copy()
    query.pop("page", None)
    context["querystring"] = query.urlencode()
    result_query = request.GET.copy()
    result_query.pop("results_page", None)
    context["results_querystring"] = result_query.urlencode()
    return render(
        request,
        "email_marketing/client/workspace.html",
        context,
        status=200 if form.is_valid() else 400,
    )


@login_required
def detail(request, pk):
    organization = _organization(request)
    work = _get(selectors.work_for(request.user, organization), pk)
    return render(
        request,
        "email_marketing/client/detail.html",
        {
            "organization": organization,
            "portal_key": "email_marketing",
            "page_title": work.name,
            "work": work,
            "cards": selectors.delivery_cards(request.user, organization, work),
            "can_review": policies.can_review(request.user, organization),
            "results": selectors.metrics_for(request.user, organization).filter(work=work)[:31],
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def review(request, pk):
    organization = _organization(request)
    approval = _get(selectors.reviews_for(request.user, organization), pk)
    form = forms.DecisionForm(request.POST if request.method == "POST" else None)
    can_review = policies.can_review(request.user, organization)
    if request.method == "POST":
        if not can_review:
            raise PermissionDenied("Your membership is read-only.")
        if form.is_valid():
            try:
                services.decide_review(
                    actor=request.user,
                    organization=organization,
                    approval=approval,
                    **form.cleaned_data,
                )
            except ValidationError as exc:
                form.add_error(None, "; ".join(exc.messages))
            else:
                messages.success(request, "Your review has been recorded.")
                return redirect(
                    "organizations:email_marketing_detail", pk=approval.deliverable.work_id
                )
    return render(
        request,
        "email_marketing/client/review.html",
        {
            "organization": organization,
            "portal_key": "email_marketing",
            "page_title": "Review deliverable",
            "approval": approval,
            "form": form,
            "can_review": can_review,
        },
        status=400 if request.method == "POST" and form.errors else 200,
    )
