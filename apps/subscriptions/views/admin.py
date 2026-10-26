"""Staff management of client services.

Every route is guarded twice over: `@require_permission` opens the page,
and the service layer re-checks the permission **against the client the
record belongs to** before anything changes. The second check is the one
that matters — a staff member assigned to three clients holds
`subscriptions_edit` for all of them, and must not be able to touch a
fourth client's retainer by typing its id.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.permissions.guards import require_permission
from apps.subscriptions import selectors, services
from apps.subscriptions.forms import (
    SubscriptionForm,
    SubscriptionNoteForm,
    SubscriptionStatusForm,
)
from apps.subscriptions.models import SubscriptionStatus

PER_PAGE = 25

BREADCRUMB = [{"label": "Client services", "href": "/staff/subscriptions/"}]


def _shell(title: str, subtitle: str = "", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": "subscriptions", **extra}


@require_permission("subscriptions_view")
def subscription_list(request: HttpRequest) -> HttpResponse:
    """Everything the agency is delivering, scoped to this actor."""
    status = request.GET.get("status", "")
    search = (request.GET.get("q") or "").strip()

    subscriptions = selectors.visible_subscriptions(
        request.user, status=status, search=search,
    )
    counts = selectors.status_counts(request.user)

    paginator = Paginator(subscriptions, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    querystring = "&".join(
        f"{key}={value}" for key, value in (("status", status), ("q", search))
        if value
    )

    return render(request, "subscriptions/admin/list.html", _shell(
        "Client services",
        "What each client is paying for, and what that opens in their "
        "workspace.",
        page_obj=page_obj, subscriptions=page_obj.object_list,
        status=status, search=search, querystring=querystring,
        is_filtered=bool(status or search),
        expiring=selectors.expiring_soon(request.user)[:5],
        stages=[{"value": value, "label": label, "count": counts.get(value, 0)}
                for value, label in SubscriptionStatus.choices],
        columns=[{"label": "Client"}, {"label": "Service"},
                 {"label": "Status"}, {"label": "Price"}, {"label": "Period"}],
    ))


def _subscription_or_404(request: HttpRequest, pk: int):  # noqa: ANN202
    subscription = selectors.get_subscription(request.user, pk)
    if subscription is None:
        # 404 rather than 403: confirming that another client's service
        # exists is itself information.
        raise Http404("No such client service.")
    return subscription


@require_permission("subscriptions_view")
def subscription_detail(request: HttpRequest, pk: int) -> HttpResponse:
    subscription = _subscription_or_404(request, pk)

    from apps.subscriptions.workspace import staff_project

    return render(request, "subscriptions/admin/detail.html", _shell(
        subscription.name, subscription.organization.label,
        **staff_project(request.user, subscription),
        subscription=subscription,
        events=subscription.events.all(),
        form=SubscriptionForm.for_subscription(subscription),
        status_form=SubscriptionStatusForm(subscription=subscription),
        note_form=SubscriptionNoteForm(),
        module=subscription.workspace_module,
        breadcrumbs=BREADCRUMB,
    ))


@require_permission("subscriptions_create")
@require_http_methods(["GET", "POST"])
def subscription_create(request: HttpRequest, slug: str) -> HttpResponse:
    """Attach a service to a client by hand.

    The manual path. It produces the same rows through the same service
    function as an accepted quote does, so the two cannot drift apart.
    """
    from apps.organizations import selectors as organization_selectors

    organization = organization_selectors.get_organization(request.user, slug)
    if organization is None:
        raise Http404("No such client.")

    form = SubscriptionForm(request.POST or None, organization=organization)

    if request.method == "POST" and form.is_valid():
        try:
            subscription = services.create_subscription(
                organization=organization, actor=request.user,
                **{key: value for key, value in form.cleaned_data.items()
                   if key != "status"},
            )
        except PermissionDenied:
            raise
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(
                request,
                _("%(name)s added for %(client)s. It is pending until you "
                  "activate it.") % {"name": subscription.name,
                                     "client": organization.label},
            )
            return redirect("staff:subscription_detail", pk=subscription.pk)

    return render(request, "subscriptions/admin/form.html", _shell(
        f"Add a service for {organization.label}",
        "Pricing is copied from the catalogue and can then be adjusted for "
        "this client.",
        form=form, organization=organization,
        breadcrumbs=BREADCRUMB,
    ))


def _back(subscription) -> HttpResponse:  # noqa: ANN001
    return redirect("staff:subscription_detail", pk=subscription.pk)


@require_permission("subscriptions_edit")
@require_http_methods(["POST"])
def subscription_update(request: HttpRequest, pk: int) -> HttpResponse:
    subscription = _subscription_or_404(request, pk)
    form = SubscriptionForm(request.POST, organization=subscription.organization,
                            instance=subscription)

    if form.is_valid():
        try:
            services.update_subscription(
                subscription=subscription, actor=request.user,
                **{key: value for key, value in form.cleaned_data.items()
                   if key != "service"},
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Service updated."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return _back(subscription)


@require_permission("subscriptions_view")
@require_http_methods(["POST"])
def subscription_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Activate, pause, complete or cancel.

    Guarded at `view` here and at `approve` in the service layer, against
    this client. Deciding that in one place means the rule holds for
    every caller, including the quote path.
    """
    subscription = _subscription_or_404(request, pk)
    form = SubscriptionStatusForm(request.POST, subscription=subscription)

    if form.is_valid():
        try:
            services.change_status(
                subscription=subscription, status=form.cleaned_data["status"],
                actor=request.user, note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        except PermissionDenied:
            messages.error(request, _("You may not change this service's status."))
        else:
            messages.success(request, _("Status updated."))
    else:
        messages.error(request, _("That is not a move this service can make."))

    return _back(subscription)


@require_permission("subscriptions_edit")
@require_http_methods(["POST"])
def subscription_note(request: HttpRequest, pk: int) -> HttpResponse:
    subscription = _subscription_or_404(request, pk)
    form = SubscriptionNoteForm(request.POST)

    if form.is_valid():
        services.add_note(
            subscription=subscription, body=form.cleaned_data["body"],
            actor=request.user,
            is_internal=not form.cleaned_data.get("share_with_client"),
        )
        messages.success(request, _("Note added."))
    else:
        messages.error(request, _("A note needs something in it."))

    return _back(subscription)


@require_permission("subscriptions_create")
@require_http_methods(["POST"])
def subscription_from_quote(request: HttpRequest, pk: int) -> HttpResponse:
    """Turn an accepted quote into the services it agreed to."""
    from apps.leads import selectors as lead_selectors

    quote = lead_selectors.get_quote_request(request.user, pk)
    if quote is None:
        raise Http404("No such quote request.")

    try:
        created, skipped = services.create_from_quote(quote=quote,
                                                      actor=request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    except PermissionDenied:
        messages.error(request, _("You may not add services for this client."))
    else:
        if created:
            messages.success(
                request,
                _("%(count)s service(s) added for %(client)s, pending "
                  "activation.") % {"count": len(created),
                                    "client": quote.organization.label},
            )
        if skipped:
            # Said out loud rather than dropped silently: a line that did
            # not become a service is exactly the thing somebody needs to
            # know about.
            messages.warning(
                request,
                _("Not added: %(lines)s.") % {"lines": "; ".join(skipped)},
            )
        if not created and not skipped:
            messages.info(request, _("That quote had no services to add."))

    return redirect("staff:quote_detail", pk=quote.pk)
