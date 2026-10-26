"""Staff management of external integrations.

`/staff/integrations/` lists every provider this platform knows an
adapter for, whether or not anything is connected yet — a provider with
no connections still needs to be visible, because "not configured" is
itself the answer most of this page gives today, and the brief is
explicit that this must be shown honestly rather than omitted.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.integrations import selectors, services
from apps.integrations.forms import ConnectionForm, ProviderCredentialForm
from apps.integrations.models import Provider
from apps.permissions.guards import require_permission


def _shell(title: str, subtitle: str = "", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": "integrations", **extra}


@require_permission("integrations_view")
def home(request: HttpRequest) -> HttpResponse:
    """Every provider, connected or not."""
    return render(request, "integrations/admin/home.html", _shell(
        "Integrations",
        "External accounts the agency can pull analytics from. Nothing "
        "here calls a provider except a sync you start, or one run from "
        "the schedule.",
        providers=selectors.provider_overview(request.user),
        connections=selectors.visible_connections(request.user),
    ))


@require_permission("integrations_view")
def provider_detail(request: HttpRequest, provider: str) -> HttpResponse:
    if provider not in Provider.values:
        raise Http404("No such provider.")

    from apps.integrations.providers import get_adapter

    return render(request, "integrations/admin/provider.html", _shell(
        dict(Provider.choices)[provider], "Connections and sync history.",
        provider=provider, provider_label=dict(Provider.choices)[provider],
        has_adapter=get_adapter(provider) is not None,
        connections=selectors.visible_connections(request.user, provider=provider),
        history=selectors.sync_history(request.user, provider=provider, limit=20),
        form=ConnectionForm(),
        credential_form=ProviderCredentialForm(provider=provider),
        credential_status=selectors.credential_status(request.user, provider),
        columns=[{"label": "Client"}, {"label": "Account"}, {"label": "Status"},
                 {"label": "Last sync"}, {"label": "", "align": "right"}],
    ))


@require_permission("integrations_manage")
@require_http_methods(["POST"])
def credentials_update(request: HttpRequest, provider: str) -> HttpResponse:
    """Save the app-level credential fields for one provider.

    The one place `META_APP_SECRET`-style values are ever written —
    from the dashboard, encrypted at rest, so a credential can be
    entered or rotated without a redeploy. See
    `apps.integrations.credentials` for which fields each provider
    asks for.
    """
    if provider not in Provider.values:
        raise Http404("No such provider.")

    form = ProviderCredentialForm(request.POST, provider=provider)
    if form.is_valid():
        services.set_credentials(provider=provider, actor=request.user,
                                 **form.cleaned_data)
        messages.success(request, _("Credentials saved."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:integration_provider", provider=provider)


@require_permission("integrations_manage")
@require_http_methods(["POST"])
def connection_create(request: HttpRequest, provider: str) -> HttpResponse:
    if provider not in Provider.values:
        raise Http404("No such provider.")

    organization = None
    slug = request.POST.get("organization_slug", "")
    if slug:
        from apps.organizations import selectors as organization_selectors

        organization = organization_selectors.get_organization(request.user, slug)
        if organization is None:
            raise Http404("No such client.")

    form = ConnectionForm(request.POST)
    if form.is_valid():
        try:
            services.create_connection(
                provider=provider, organization=organization,
                actor=request.user, **form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Connection added."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:integration_provider", provider=provider)


def _connection_or_404(request: HttpRequest, pk: int):  # noqa: ANN202
    connection = selectors.get_connection(request.user, pk)
    if connection is None:
        raise Http404("No such connection.")
    return connection


@require_permission("integrations_manage")
@require_http_methods(["POST"])
def connection_update(request: HttpRequest, pk: int) -> HttpResponse:
    connection = _connection_or_404(request, pk)
    form = ConnectionForm(request.POST)

    if form.is_valid():
        services.update_connection(connection=connection, actor=request.user,
                                   **form.cleaned_data)
        messages.success(request, _("Connection updated."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:integration_provider", provider=connection.provider)


@require_permission("integrations_manage")
@require_http_methods(["POST"])
def connection_disconnect(request: HttpRequest, pk: int) -> HttpResponse:
    connection = _connection_or_404(request, pk)
    services.disconnect(connection=connection, actor=request.user)
    messages.success(request, _("Disconnected."))
    return redirect("staff:integration_provider", provider=connection.provider)


@require_permission("integrations_manage")
@require_http_methods(["POST"])
def sync_now(request: HttpRequest, provider: str) -> HttpResponse:
    """Run a sync immediately, from the dashboard rather than cron.

    Calls exactly `apps.integrations.services.run_sync` — the same
    function the management commands use — so a manual sync and a
    scheduled one can never behave differently.
    """
    if provider not in Provider.values:
        raise Http404("No such provider.")

    organization = None
    slug = request.POST.get("organization_slug", "")
    if slug:
        from apps.organizations import selectors as organization_selectors

        organization = organization_selectors.get_organization(request.user, slug)

    try:
        run = services.run_sync(provider=provider, organization=organization,
                                actor=request.user)
    except PermissionDenied:
        messages.error(request, _("You may not run a sync."))
    else:
        if run.status == "success":
            messages.success(request, _("Sync completed."))
        elif run.status == "skipped":
            messages.info(request, _("Sync skipped: %(reason)s")
                         % {"reason": run.error_summary or _("not configured")})
        else:
            messages.warning(request, _("Sync did not complete. See the "
                                        "history below."))

    return redirect("staff:integration_provider", provider=provider)


@require_permission("integrations_view")
def sync_history(request: HttpRequest) -> HttpResponse:
    return render(request, "integrations/admin/history.html", _shell(
        "Sync history", "Every attempt, whatever the result.",
        history=selectors.sync_history(request.user, limit=100),
        columns=[{"label": "Provider"}, {"label": "Client"}, {"label": "Started"},
                 {"label": "Status"}, {"label": "Records"}],
    ))
