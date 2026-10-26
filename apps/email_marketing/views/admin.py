"""Staff email_marketing workspace; each URL also checks client assignment."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.email_marketing import forms, policies, selectors, services
from apps.organizations import selectors as organizations
from apps.permissions.guards import require_permission, scope_to_accessible


def _organization(request, slug):
    organization = organizations.get_organization(request.user, slug)
    if not policies.can_read(request.user, organization):
        raise Http404("No such workspace.")
    return organization


def _get(queryset, pk):
    try:
        obj = queryset.filter(pk=pk).first()
    except (ValidationError, ValueError):
        raise Http404("No such email marketing record.") from None
    if obj is None:
        raise Http404("No such email marketing record.")
    return obj


def _context(request, organization):
    return {
        "organization": organization,
        "nav_key": "email_marketing",
        "page_title": "Email Marketing",
        "is_staff_workspace": True,
        "can_create": policies.can_write(request.user, organization),
        "can_edit": policies.can_write(request.user, organization, "edit"),
    }


def _form_page(request, organization, form, heading, save, work=None):
    if request.method == "POST" and form.is_valid():
        try:
            record = save(**form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Email marketing work saved.")
            if work:
                return redirect("staff:email_marketing_detail", slug=organization.slug, pk=work.pk)
            if isinstance(form, forms.WorkForm):
                return redirect(
                    "staff:email_marketing_detail", slug=organization.slug, pk=record.pk
                )
            return redirect("staff:email_marketing_workspace", slug=organization.slug)
    return render(
        request,
        "email_marketing/admin/form.html",
        {**_context(request, organization), "form": form, "heading": heading},
        status=400 if request.method == "POST" and form.errors else 200,
    )


@require_permission("email_marketing_view")
def home(request):
    rows = scope_to_accessible(
        organizations.visible_organizations(request.user), request.user, field="id"
    ).order_by("name")
    return render(
        request,
        "email_marketing/admin/home.html",
        {
            "nav_key": "email_marketing",
            "page_title": "Email Marketing",
            "page_obj": Paginator(rows, 25).get_page(request.GET.get("page")),
        },
    )


@require_permission("email_marketing_view")
def workspace(request, slug):
    organization = _organization(request, slug)
    form = forms.FilterForm(request.GET, actor=request.user, organization=organization)
    context = {
        **_context(request, organization),
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
        "email_marketing/admin/workspace.html",
        context,
        status=200 if form.is_valid() else 400,
    )


def _edit(request, slug, pk=None):
    organization = _organization(request, slug)
    instance = _get(selectors.work_for(request.user, organization), pk) if pk else None
    form = forms.WorkForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
        organization=organization,
        instance=instance,
    )
    return _form_page(
        request,
        organization,
        form,
        "Edit email work" if pk else "New email work",
        lambda **data: services.save_work(
            actor=request.user, organization=organization, work=instance, **data
        ),
    )


@require_permission("email_marketing_create")
@require_http_methods(["GET", "POST"])
def create(request, slug):
    return _edit(request, slug)


@require_permission("email_marketing_edit")
@require_http_methods(["GET", "POST"])
def edit(request, slug, pk):
    return _edit(request, slug, pk)


@require_permission("email_marketing_view")
def detail(request, slug, pk):
    organization = _organization(request, slug)
    work = _get(selectors.work_for(request.user, organization), pk)
    return render(
        request,
        "email_marketing/admin/detail.html",
        {
            **_context(request, organization),
            "work": work,
            "cards": selectors.delivery_cards(request.user, organization, work),
            "results": selectors.metrics_for(request.user, organization).filter(work=work)[:31],
        },
    )


@require_permission("email_marketing_create")
@require_http_methods(["GET", "POST"])
def deliverable_create(request, slug, pk):
    return _deliverable_form(request, slug, pk)


@require_permission("email_marketing_edit")
@require_http_methods(["GET", "POST"])
def deliverable_edit(request, slug, pk, delivery_id):
    return _deliverable_form(request, slug, pk, delivery_id)


def _deliverable_form(request, slug, pk, delivery_id=None):
    organization = _organization(request, slug)
    work = _get(selectors.work_for(request.user, organization), pk)
    delivery = (
        _get(
            selectors.deliverables_for(request.user, organization).filter(work=work),
            delivery_id,
        )
        if delivery_id
        else None
    )
    form = forms.DeliverableForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
        organization=organization,
        work=work,
        instance=delivery,
    )
    return _form_page(
        request,
        organization,
        form,
        "Deliverable",
        lambda **data: services.save_deliverable(
            actor=request.user,
            organization=organization,
            work=work,
            deliverable=delivery,
            **data,
        ),
        work,
    )


@require_permission("email_marketing_edit")
@require_POST
def request_review(request, slug, pk, delivery_id):
    organization = _organization(request, slug)
    delivery = _get(
        selectors.deliverables_for(request.user, organization).filter(work_id=pk), delivery_id
    )
    try:
        services.request_review(actor=request.user, organization=organization, deliverable=delivery)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Client review requested.")
    return redirect("staff:email_marketing_detail", slug=slug, pk=pk)


@require_permission("email_marketing_edit")
@require_http_methods(["GET", "POST"])
def status(request, slug, pk):
    organization = _organization(request, slug)
    work = _get(selectors.work_for(request.user, organization), pk)
    form = forms.StatusForm(
        request.POST if request.method == "POST" else None,
        work=work,
        can_record_execution=policies.can_write(request.user, organization, "publish"),
    )
    return _form_page(
        request,
        organization,
        form,
        "Record work status (no email is sent)",
        lambda **data: services.change_status(
            actor=request.user, organization=organization, work=work, **data
        ),
        work,
    )


@require_permission("email_marketing_create")
@require_http_methods(["GET", "POST"])
def metrics(request, slug, pk):
    organization = _organization(request, slug)
    work = _get(selectors.work_for(request.user, organization), pk)
    form = forms.MetricForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
        organization=organization,
        work=work,
    )
    return _form_page(
        request,
        organization,
        form,
        "Record daily results",
        lambda **data: services.record_metrics(
            actor=request.user, organization=organization, work=work, **data
        ),
        work,
    )
