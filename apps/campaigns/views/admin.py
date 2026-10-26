"""Staff management of campaigns.

One list across every service area — which is what the supplied dashboard
shows, and the reason there is a single campaign table rather than one
per module.

Every route is guarded twice: `@require_permission` opens the page, and
the service layer re-checks the permission **against the client the
campaign belongs to** before anything changes. The second is the one that
matters, because a specialist assigned to three clients holds the
permission for all of them.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.campaigns import selectors, services
from apps.campaigns.forms import (
    CampaignAssignForm,
    CampaignForm,
    CampaignNoteForm,
    CampaignStatusForm,
)
from apps.campaigns.models import CampaignStatus
from apps.campaigns.registry import all_types, detail_form_for, detail_model_for
from apps.permissions.guards import require_permission

PER_PAGE = 25

BREADCRUMB = [{"label": "Campaigns", "href": "/staff/campaigns/"}]


def _shell(title: str, subtitle: str = "", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": "campaigns", **extra}


@require_permission("campaigns_view")
def campaign_list(request: HttpRequest) -> HttpResponse:
    """Every campaign, across every service, filtered and searchable."""
    status = request.GET.get("status", "")
    service_type = request.GET.get("type", "")
    owner = request.GET.get("owner", "")
    search = (request.GET.get("q") or "").strip()

    campaigns = selectors.visible_campaigns(
        request.user, status=status, service_type=service_type,
        owner=owner, search=search,
    )
    counts = selectors.status_counts(request.user, service_type=service_type)
    by_type = selectors.type_counts(request.user)

    paginator = Paginator(campaigns, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    querystring = "&".join(
        f"{key}={value}" for key, value in
        (("status", status), ("type", service_type), ("owner", owner),
         ("q", search))
        if value
    )

    return render(request, "campaigns/admin/list.html", _shell(
        "Campaigns",
        "Everything running across every service, for every client you "
        "work with.",
        page_obj=page_obj, campaigns=page_obj.object_list,
        status=status, service_type=service_type, owner=owner, search=search,
        querystring=querystring,
        is_filtered=bool(status or service_type or owner or search),
        stages=[{"value": value, "label": label, "count": counts.get(value, 0)}
                for value, label in CampaignStatus.choices],
        types=[{"value": t.key, "label": t.label,
                "count": by_type.get(t.key, 0)} for t in all_types()],
        overdue=selectors.overdue(request.user)[:5],
        columns=[{"label": "Campaign"}, {"label": "Client"},
                 {"label": "Area"}, {"label": "Status"}, {"label": "Period"}],
    ))


def _campaign_or_404(request: HttpRequest, pk: int):  # noqa: ANN202
    campaign = selectors.get_campaign(request.user, pk)
    if campaign is None:
        # 404 rather than 403: confirming that another client's campaign
        # exists is itself information.
        raise Http404("No such campaign.")
    return campaign


@require_permission("campaigns_view")
def campaign_detail(request: HttpRequest, pk: int) -> HttpResponse:
    campaign = _campaign_or_404(request, pk)

    detail_form_class = detail_form_for(campaign.service_type)
    detail_form = None
    if detail_form_class is not None:
        detail_model = detail_model_for(campaign.service_type)
        detail_form = detail_form_class(
            instance=campaign.detail or detail_model(campaign=campaign))

    from apps.integrations import selectors as integration_selectors
    from apps.integrations.forms import CampaignMappingForm

    return render(request, "campaigns/admin/detail.html", _shell(
        campaign.name, campaign.organization.label,
        campaign=campaign,
        events=campaign.events.all(),
        form=CampaignForm.for_campaign(campaign),
        status_form=CampaignStatusForm(campaign=campaign),
        assign_form=CampaignAssignForm(initial={
            "owner": campaign.owner_id,
            "assignees": campaign.assignees.values_list("pk", flat=True),
        }),
        note_form=CampaignNoteForm(),
        detail=campaign.detail,
        detail_form=detail_form,
        mappings=integration_selectors.mappings_for_campaign(request.user, campaign),
        mapping_form=CampaignMappingForm(organization=campaign.organization),
        breadcrumbs=BREADCRUMB,
    ))


@require_permission("campaigns_create")
@require_http_methods(["GET", "POST"])
def campaign_create(request: HttpRequest, slug: str) -> HttpResponse:
    """Start a campaign for one client."""
    from apps.organizations import selectors as organization_selectors

    organization = organization_selectors.get_organization(request.user, slug)
    if organization is None:
        raise Http404("No such client.")

    form = CampaignForm(request.POST or None, organization=organization,
                        initial={"service_type": request.GET.get("service_type", "")})

    if request.method == "POST" and form.is_valid():
        try:
            campaign = services.create_campaign(
                organization=organization, actor=request.user,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(
                request,
                _("%(name)s created. It is planned until you take it live.")
                % {"name": campaign.name},
            )
            return redirect("staff:campaign_detail", pk=campaign.pk)

    return render(request, "campaigns/admin/form.html", _shell(
        f"New campaign for {organization.label}",
        "It starts as planned. Taking it live is a separate step.",
        form=form, organization=organization, breadcrumbs=BREADCRUMB,
    ))


def _back(campaign) -> HttpResponse:  # noqa: ANN001
    return redirect("staff:campaign_detail", pk=campaign.pk)


@require_permission("campaigns_edit")
@require_http_methods(["POST"])
def campaign_update(request: HttpRequest, pk: int) -> HttpResponse:
    campaign = _campaign_or_404(request, pk)
    form = CampaignForm(request.POST, organization=campaign.organization,
                        instance=campaign)

    if form.is_valid():
        try:
            services.update_campaign(campaign=campaign, actor=request.user,
                                     **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Campaign updated."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return _back(campaign)


@require_permission("campaigns_edit")
@require_http_methods(["POST"])
def campaign_detail_update(request: HttpRequest, pk: int) -> HttpResponse:
    """Save the service area's own fields — a paid campaign's platform
    and objective, an SEO campaign's focus, and so on.

    Resolved generically through the registry rather than branching on
    `service_type` here: this view has never heard of `PaidAdsCampaignDetail`
    and never will, which is the whole point of the extension point in
    `apps.campaigns.registry`.
    """
    campaign = _campaign_or_404(request, pk)
    detail_model = detail_model_for(campaign.service_type)
    detail_form_class = detail_form_for(campaign.service_type)
    if detail_model is None or detail_form_class is None:
        raise Http404("This service area has nothing here to edit.")

    instance = campaign.detail or detail_model(campaign=campaign)
    form = detail_form_class(request.POST, instance=instance)

    if form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return _back(campaign)


@require_permission("campaigns_edit")
@require_http_methods(["POST"])
def campaign_map_external(request: HttpRequest, pk: int) -> HttpResponse:
    """Point this campaign at its real counterpart at a provider.

    The step between "the campaign exists" and "analytics can sync for
    it" — see `apps.integrations.services.map_campaign`. Nothing is
    fetched here; this only records which external campaign ID this
    one *is*, so a later sync knows where to attribute what it reads.
    """
    from apps.integrations import services as integration_services
    from apps.integrations.forms import CampaignMappingForm

    campaign = _campaign_or_404(request, pk)
    form = CampaignMappingForm(request.POST, organization=campaign.organization)

    if form.is_valid():
        try:
            integration_services.map_campaign(
                campaign=campaign, actor=request.user, **form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Campaign mapped. A sync will pick "
                                        "up its results next time it runs."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return _back(campaign)


@require_permission("campaigns_view")
@require_http_methods(["POST"])
def campaign_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Take it live, pause it, finish it or call it off.

    Guarded at `view` here and at `approve` in the service layer, against
    this client. Deciding that in one place means the rule holds for
    every caller.
    """
    campaign = _campaign_or_404(request, pk)
    form = CampaignStatusForm(request.POST, campaign=campaign)

    if form.is_valid():
        try:
            services.change_status(
                campaign=campaign, status=form.cleaned_data["status"],
                actor=request.user, note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        except PermissionDenied:
            messages.error(request, _("You may not change this campaign's status."))
        else:
            messages.success(request, _("Status updated."))
    else:
        messages.error(request, _("That is not a move this campaign can make."))

    return _back(campaign)


@require_permission("campaigns_assign")
@require_http_methods(["POST"])
def campaign_assign(request: HttpRequest, pk: int) -> HttpResponse:
    campaign = _campaign_or_404(request, pk)
    form = CampaignAssignForm(request.POST)

    if form.is_valid():
        services.assign(
            campaign=campaign, actor=request.user,
            owner=form.cleaned_data["owner"],
            assignees=list(form.cleaned_data["assignees"]),
        )
        messages.success(request, _("People updated."))
    else:
        messages.error(request, _("That could not be saved."))

    return _back(campaign)


@require_permission("campaigns_edit")
@require_http_methods(["POST"])
def campaign_note(request: HttpRequest, pk: int) -> HttpResponse:
    campaign = _campaign_or_404(request, pk)
    form = CampaignNoteForm(request.POST)

    if form.is_valid():
        services.add_note(
            campaign=campaign, body=form.cleaned_data["body"],
            actor=request.user,
            is_internal=not form.cleaned_data.get("share_with_client"),
        )
        messages.success(request, _("Note added."))
    else:
        messages.error(request, _("A note needs something in it."))

    return _back(campaign)
