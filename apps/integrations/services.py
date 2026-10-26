"""Write operations for the Integrations domain.

`run_sync` is the one function a management command or an admin "Sync
Now" button calls. Everything it does is wrapped so that a provider
failure — an expired token, a network error, credentials nobody has
configured yet — becomes an `AnalyticsSyncRun` row and an in-app
notification, never an unhandled exception that would take the whole
cron invocation down with it.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.features import require
from apps.integrations import policies
from apps.integrations.models import (
    AnalyticsSyncRun,
    ConnectionStatus,
    ExternalCampaignReference,
    IntegrationConnection,
    SyncStatus,
)
from apps.integrations.providers.base import ProviderNotConfigured

logger = logging.getLogger(__name__)


@transaction.atomic
def create_connection(*, provider: str, actor, organization=None,  # noqa: ANN001
                      **fields) -> IntegrationConnection:
    require(provider, actor)

    if not policies.can_manage_integrations(actor):
        raise PermissionDenied("You may not configure integrations.")

    connection = IntegrationConnection(
        provider=provider, organization=organization,
        created_by=actor if getattr(actor, "pk", None) else None,
        **fields,
    )
    connection.full_clean()
    connection.save()
    return connection


@transaction.atomic
def set_credentials(*, provider: str, actor, **fields) -> None:
    """Save the app-level credential fields for one provider.

    Blank means "leave the stored value unchanged" — the same
    convention `ConnectionForm` uses for a connection's own token,
    since these fields are masked and never pre-filled, so a blank
    submission cannot otherwise be told apart from "clear this."
    """
    from apps.integrations.models import ProviderCredential

    require(provider, actor)

    if not policies.can_manage_integrations(actor):
        raise PermissionDenied("You may not configure integrations.")

    for key, value in fields.items():
        if not value:
            continue
        ProviderCredential.objects.update_or_create(
            provider=provider, key=key,
            defaults={"value": value,
                     "updated_by": actor if getattr(actor, "pk", None) else None},
        )


@transaction.atomic
def update_connection(*, connection: IntegrationConnection, actor,  # noqa: ANN001
                      **fields) -> IntegrationConnection:
    require(connection.provider, actor)

    if not policies.can_manage_integrations(actor):
        raise PermissionDenied("You may not configure integrations.")

    editable = {"display_name", "external_account_id", "access_token",
                "refresh_token", "client_secret", "token_expires_at"}
    changed = [field for field, value in fields.items()
              if field in editable and getattr(connection, field) != value]
    for field in changed:
        setattr(connection, field, fields[field])

    if changed:
        # A fresh set of credentials deserves a fresh chance — the status
        # moves back to "not configured" (re-evaluated on the next sync)
        # rather than keeping a stale "error" badge from the old token.
        connection.status = ConnectionStatus.NOT_CONFIGURED
        connection.status_detail = ""
        connection.full_clean()
        connection.save(update_fields=[*changed, "status", "status_detail",
                                       "updated_at"])
    return connection


@transaction.atomic
def disconnect(*, connection: IntegrationConnection, actor) -> IntegrationConnection:  # noqa: ANN001
    require(connection.provider, actor)

    if not policies.can_manage_integrations(actor):
        raise PermissionDenied("You may not configure integrations.")

    connection.status = ConnectionStatus.DISCONNECTED
    connection.access_token = ""
    connection.refresh_token = ""
    connection.save(update_fields=["status", "access_token", "refresh_token",
                                   "updated_at"])
    return connection


@transaction.atomic
def map_campaign(*, campaign, connection: IntegrationConnection,  # noqa: ANN001
                 external_campaign_id: str, actor, **fields) -> ExternalCampaignReference:
    """Point one of our campaigns at its external counterpart.

    There is no OAuth campaign picker in this version — the external
    campaign ID is typed in by whoever set the ad up, because nothing
    here has ever called the provider's API to list campaigns. A mapping
    entered this way is exactly as trustworthy as whoever typed it, and
    no more.
    """
    from apps.campaigns import policies as campaign_policies

    require(connection.provider, actor)

    if not campaign_policies.can_edit_campaigns(actor, campaign.organization):
        raise PermissionDenied("You may not map this campaign.")

    if connection.organization_id is not None and \
            connection.organization_id != campaign.organization_id:
        raise ValidationError(
            "That connection belongs to a different client than the "
            "campaign."
        )

    reference = ExternalCampaignReference(
        campaign=campaign, connection=connection,
        external_campaign_id=external_campaign_id.strip(), **fields,
    )
    reference.full_clean()
    reference.save()
    return reference


def run_sync(*, provider: str, organization=None, actor=None,  # noqa: ANN001
             days: int = 7) -> AnalyticsSyncRun:
    """Attempt a sync for one connection, and always leave a record of it.

    This is the one path every entry point uses: `python manage.py
    sync_meta_analytics`, the admin "Sync Now" button, and any future
    scheduled trigger all call this and nothing lower-level. If the
    provider is unconfigured, or anything else goes wrong, the run is
    still written — `skipped` or `failed` rather than absent — because a
    sync that never happened and a sync nobody recorded look identical
    to anyone checking later, and only one of those is true.
    """
    from apps.integrations.models import Provider
    from apps.integrations.providers import get_adapter

    connection = None
    if organization is not None:
        connection = IntegrationConnection.objects.filter(
            organization=organization, provider=provider).first()
    elif provider not in {Provider.RUDDERSTACK}:
        connection = IntegrationConnection.objects.filter(
            provider=provider, organization__isnull=True).first()

    run = AnalyticsSyncRun.objects.create(
        provider=provider, connection=connection, organization=organization,
        status=SyncStatus.RUNNING,
        triggered_by=actor if getattr(actor, "pk", None) else None,
    )

    from apps.core.features import enabled

    if not enabled("integrations") or not enabled(provider):
        _finish(run, status=SyncStatus.SKIPPED,
                error_summary="External integrations are disabled by the website owner.")
        return run

    adapter = get_adapter(provider)
    if adapter is None:
        _finish(run, status=SyncStatus.SKIPPED,
               error_summary=f"No adapter is registered for {provider}.")
        return run

    if connection is None:
        _finish(run, status=SyncStatus.SKIPPED,
               error_summary="No connection has been configured yet.")
        return run

    end = timezone.localdate()
    start = end - timedelta(days=days)

    try:
        metrics = adapter.sync(connection, start=start, end=end)
    except ProviderNotConfigured as exc:
        connection.status = ConnectionStatus.NOT_CONFIGURED
        connection.status_detail = str(exc)[:300]
        connection.last_sync_at = timezone.now()
        connection.save(update_fields=["status", "status_detail",
                                       "last_sync_at", "updated_at"])
        _finish(run, status=SyncStatus.SKIPPED, error_summary=str(exc)[:300])
        return run
    except Exception as exc:  # noqa: BLE001 - a sync must never crash the caller
        logger.exception("Sync failed for %s (%s)", provider, organization)
        connection.status = ConnectionStatus.ERROR
        connection.status_detail = "The last sync attempt failed."
        connection.last_sync_at = timezone.now()
        connection.save(update_fields=["status", "status_detail",
                                       "last_sync_at", "updated_at"])
        _finish(run, status=SyncStatus.FAILED, error_summary=str(exc)[:300])
        _notify_sync_failure(provider=provider, organization=organization)
        return run

    created, updated = _write_metrics(provider=provider, metrics=metrics)

    connection.status = ConnectionStatus.CONNECTED
    connection.status_detail = ""
    connection.last_sync_at = timezone.now()
    connection.last_successful_sync_at = connection.last_sync_at
    connection.save(update_fields=["status", "status_detail", "last_sync_at",
                                   "last_successful_sync_at", "updated_at"])

    run.records_received = len(metrics)
    run.records_created = created
    run.records_updated = updated
    _finish(run, status=SyncStatus.SUCCESS if metrics else SyncStatus.PARTIAL)
    return run


def _finish(run: AnalyticsSyncRun, *, status: str, error_summary: str = "") -> None:
    run.status = status
    run.error_summary = error_summary
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error_summary", "finished_at",
                            "records_received", "records_created",
                            "records_updated"])


def _write_metrics(*, provider: str, metrics) -> tuple[int, int]:  # noqa: ANN001
    """Route normalized metrics to the owning domain's own metric table.

    This platform already has one metric model per delivery domain
    (`paid_ads.DailyAdMetric`, future equivalents for social and email) —
    see `docs/ANALYTICS.md` for why that beats one shared table. An
    adapter's job ends at producing `NormalizedMetrics`; which table they
    land in is a decision only the owning domain should make, so this
    looks the mapped campaign up and asks its domain to store them rather
    than writing to a table by provider name.
    """
    if not metrics:
        return 0, 0

    created = updated = 0
    for row in metrics:
        references = ExternalCampaignReference.objects.filter(
            external_campaign_id=row.external_campaign_id,
        ).select_related("campaign")
        for reference in references:
            reference.last_synced_at = timezone.now()
            reference.save(update_fields=["last_synced_at", "updated_at"])

            was_created = _store_for_campaign(
                campaign=reference.campaign, provider=provider, row=row,
            )
            if was_created:
                created += 1
            else:
                updated += 1

    return created, updated


def _store_for_campaign(*, campaign, provider: str, row) -> bool:  # noqa: ANN001
    """Write one day's normalized metrics into the owning domain's table.

    Only paid advertising has a provider-fed metric table today — social
    and email metrics are entered from the platforms' own reporting
    exports rather than a live API, per the brief's own instruction not
    to claim a live connection that was never built. A provider whose
    campaigns are not `paid_ads` is accepted and silently has nowhere to
    write yet, which is correct: there is nothing dishonest about an
    adapter existing before every domain has a writer for it.
    """
    if campaign.service_type != "paid_ads":
        return False

    from decimal import Decimal

    from apps.paid_ads.models import DailyAdMetric, Platform

    platform_by_provider = {
        "meta_ads": Platform.META, "google_ads": Platform.GOOGLE,
        "linkedin_ads": Platform.LINKEDIN, "tiktok_ads": Platform.TIKTOK,
    }
    platform = platform_by_provider.get(provider, Platform.OTHER)

    # Keyed on (campaign, platform, date) — the table's own uniqueness
    # constraint — so running the same sync twice updates this row
    # rather than duplicating it.
    _metric, created = DailyAdMetric.objects.update_or_create(
        organization=campaign.organization, campaign=campaign,
        platform=platform, date=row.date,
        defaults={
            "currency": row.currency or "USD",
            "spend": Decimal(row.spend), "impressions": row.impressions,
            "clicks": row.clicks, "leads": row.leads,
            "conversions": row.conversions, "revenue": Decimal(row.revenue),
            "reach": row.reach, "link_clicks": row.link_clicks,
            "landing_page_views": row.landing_page_views,
            "engagements": row.engagements, "video_views": row.video_views,
            "source": f"{provider} sync", "entry_method": "sync",
        },
    )

    if row.extra:
        _store_provider_metrics(campaign=campaign, provider=provider,
                                date=row.date, extra=row.extra)

    return created


def _store_provider_metrics(*, campaign, provider: str, date, extra: dict) -> None:  # noqa: ANN001
    """Overflow numbers a provider reports that the normalized table has
    no column for — see `ProviderMetric`'s own docstring."""
    from decimal import Decimal, InvalidOperation

    from apps.integrations.models import ProviderMetric

    for metric_key, numeric_value in extra.items():
        if numeric_value is None:
            continue
        try:
            decimal_value = Decimal(str(numeric_value))
        except InvalidOperation:
            continue
        ProviderMetric.objects.update_or_create(
            organization=campaign.organization, campaign=campaign,
            provider=provider, date=date, metric_key=str(metric_key)[:60],
            defaults={"numeric_value": decimal_value},
        )


def _notify_sync_failure(*, provider: str, organization) -> None:  # noqa: ANN001
    """In-app only, to whoever holds integrations rights.

    No email, no SMS — the same rule as every other domain. The client
    never sees this: they see a "last updated" time that stopped moving,
    which is honest without being alarming about something they cannot
    act on.
    """
    from apps.integrations.models import Provider
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify_permission_holders

    label = dict(Provider.choices).get(provider, provider)
    client_part = f" for {organization.label}" if organization else ""

    notify_permission_holders(
        permission="permissions.integrations_view",
        title=f"{label} synchronization failed{client_part}",
        body="Historical data is still shown. Check the connection's "
             "credentials and try again.",
        url="/staff/integrations/",
        level=NotificationLevel.WARNING,
        category="integration",
    )
