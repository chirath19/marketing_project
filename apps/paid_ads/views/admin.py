"""Staff workspaces with assignment checks on every read and write."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.organizations import selectors as organization_selectors
from apps.paid_ads import policies, selectors, services
from apps.paid_ads.forms import FilterForm, GoalForm, ImportForm, MetricForm
from apps.paid_ads.importers import import_metrics
from apps.permissions.guards import require_permission, scope_to_accessible


def _organization(request, slug):
    organization = organization_selectors.get_organization(request.user, slug)
    if not policies.can_read(request.user, organization):
        raise Http404("No such workspace.")
    return organization


def _context(request, organization):
    return {
        "page_title": f"Paid Ads — {organization.label}",
        "nav_key": "paid_ads",
        "organization": organization,
        "can_create": policies.can_write(request.user, organization),
        "can_edit": policies.can_write(request.user, organization, "edit"),
        "is_staff_workspace": True,
    }


@require_permission("paid_ads_view")
def home(request):
    organizations = scope_to_accessible(
        organization_selectors.visible_organizations(request.user),
        request.user,
        field="id",
    ).order_by("name")
    return render(
        request,
        "paid_ads/admin/home.html",
        {
            "page_title": "Paid Ads",
            "nav_key": "paid_ads",
            "page_obj": Paginator(organizations, 25).get_page(request.GET.get("page")),
        },
    )


@require_permission("paid_ads_view")
def workspace(request, slug):
    organization = _organization(request, slug)
    form = FilterForm(request.GET, actor=request.user, organization=organization)
    context = _context(request, organization)
    context["filter_form"] = form
    if form.is_valid():
        context.update(selectors.report(request.user, organization, form.cleaned_data))
        context["daily_page"] = Paginator(context["daily_rows"], 31).get_page(
            request.GET.get("page")
        )
    context["goals_url"] = reverse("staff:paid_ads_goals", args=[slug])
    query = request.GET.copy()
    query.pop("page", None)
    context["querystring"] = query.urlencode()
    return render(
        request, "paid_ads/admin/workspace.html", context, status=200 if form.is_valid() else 400
    )


@require_permission("paid_ads_create")
@require_http_methods(["GET", "POST"])
def record(request, slug):
    organization = _organization(request, slug)
    form = MetricForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
        organization=organization,
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.record_metrics(
                organization=organization, actor=request.user, **form.cleaned_data
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Daily performance saved.")
            return redirect("staff:paid_ads_workspace", slug=slug)
    return render(
        request,
        "paid_ads/admin/form.html",
        {
            **_context(request, organization),
            "form": form,
            "heading": "Record daily performance",
            "help": "Enter totals for one day. The same campaign, platform and date corrects "
            "that record and requires edit access. Currency comes from the campaign.",
        },
        status=400 if request.method == "POST" and form.errors else 200,
    )


@require_permission("paid_ads_create")
@require_http_methods(["GET", "POST"])
def import_data(request, slug):
    organization = _organization(request, slug)
    form = ImportForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            count = import_metrics(
                actor=request.user,
                organization=organization,
                file_obj=form.cleaned_data["file"],
                source=form.cleaned_data["source"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"{count} daily observation(s) imported.")
            return redirect("staff:paid_ads_workspace", slug=slug)
    return render(
        request,
        "paid_ads/admin/form.html",
        {
            **_context(request, organization),
            "form": form,
            "heading": "Import daily performance",
            "is_import": True,
            "campaigns": selectors.campaigns_for(request.user, organization),
            "help": "UTF-8 CSV, up to 5 MB and 5,000 rows. Dates use YYYY-MM-DD. "
            "Campaign is the numeric ID listed below. Platforms: google, meta, linkedin, other. "
            "All six measures are required; use 0 for a measured zero. "
            "An invalid row rejects the entire file. Existing daily keys are replaced, "
            "never added together; corrections require edit access.",
        },
        status=400 if request.method == "POST" and form.errors else 200,
    )


@require_permission("paid_ads_view")
def goals(request, slug):
    organization = _organization(request, slug)
    return render(
        request,
        "paid_ads/admin/goals.html",
        {
            **_context(request, organization),
            "page_obj": Paginator(selectors.goals_for(request.user, organization), 25).get_page(
                request.GET.get("page")
            ),
        },
    )


def _goal_form(request, organization, goal=None):
    form = GoalForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
        organization=organization,
        instance=goal,
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.save_goal(
                organization=organization, actor=request.user, goal=goal, **form.cleaned_data
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Goal saved.")
            return redirect("staff:paid_ads_goals", slug=organization.slug)
    return render(
        request,
        "paid_ads/admin/form.html",
        {
            **_context(request, organization),
            "form": form,
            "heading": "Advertising goal",
            "help": "Goals use their full inclusive date range and chosen campaign/platform. "
            "Spend and CPL are ceilings; the other measures are targets to reach. "
            "Deactivate a goal to keep it in history without showing it in the workspace.",
        },
        status=400 if request.method == "POST" and form.errors else 200,
    )


@require_permission("paid_ads_create")
@require_http_methods(["GET", "POST"])
def goal_create(request, slug):
    return _goal_form(request, _organization(request, slug))


@require_permission("paid_ads_edit")
@require_http_methods(["GET", "POST"])
def goal_edit(request, slug, pk):
    organization = _organization(request, slug)
    goal = selectors.goals_for(request.user, organization).filter(pk=pk).first()
    if goal is None:
        raise Http404("No such goal.")
    return _goal_form(request, organization, goal)
