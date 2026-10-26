"""Persistence for the Integrations domain.

Three things, and nothing fetched live: a **connection** to an external
account, a **mapping** from one of our campaigns to that account's own
campaign, and a **record of every sync attempt**. External APIs are never
called from a view or a template — only from a provider adapter, invoked
by a sync service, itself invoked by a management command. See
`apps/integrations/providers/` for the adapters and
`apps/integrations/services.py` for the orchestration.

Models hold structure and invariants only. `save()` must not grow
workflow logic.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.fields import EncryptedTextField
from apps.core.models import TimeStampedModel


class Provider(models.TextChoices):
    """Every external system this platform knows how to talk to.

    A closed list, not free text: each member has to have an adapter
    behind it (`apps.integrations.providers.get_adapter`), and a
    connection to a provider with no adapter would be a dead end nobody
    could sync.
    """

    META_ADS = "meta_ads", _("Meta Ads")
    GOOGLE_ADS = "google_ads", _("Google Ads")
    GOOGLE_ANALYTICS = "google_analytics", _("Google Analytics (GA4)")
    GOOGLE_SEARCH_CONSOLE = "google_search_console", _("Google Search Console")
    LINKEDIN_ADS = "linkedin_ads", _("LinkedIn Ads")
    TIKTOK_ADS = "tiktok_ads", _("TikTok Ads")
    RUDDERSTACK = "rudderstack", _("RudderStack")


#: Advertising providers report on exactly one client's ad account and
#: always need one chosen. See `IntegrationConnection.clean`.
REQUIRES_ORGANIZATION = frozenset({
    Provider.META_ADS, Provider.GOOGLE_ADS, Provider.LINKEDIN_ADS,
    Provider.TIKTOK_ADS,
})

#: RudderStack is agency-wide event routing configuration, not a
#: per-client analytics pull, and never attaches to one client.
FORBIDS_ORGANIZATION = frozenset({Provider.RUDDERSTACK})

#: GA4 and Search Console are genuinely dual-purpose: the **same**
#: provider reports on the agency's own marketing website
#: (`organization=None`, read by `apps.tracking`) *and* on a client's own
#: connected property, where the client purchased website analytics or
#: SEO reporting (section 14 of the brief). Neither direction is forced.


class ConnectionStatus(models.TextChoices):
    NOT_CONFIGURED = "not_configured", _("Not configured")
    CONNECTED = "connected", _("Connected")
    NEEDS_REAUTHORIZATION = "needs_reauthorization", _("Needs reauthorization")
    ERROR = "error", _("Error")
    DISCONNECTED = "disconnected", _("Disconnected")


class IntegrationConnection(TimeStampedModel):
    """One account at one provider, available for syncing.

    Secrets are stored here because they have to be stored somewhere, and
    nowhere else is more scoped than a dedicated secrets table — but
    `admin.py`, every serializer and every template read `is_configured`
    and `masked_account_id` instead. Nothing that reads a secret field
    back out exists outside `apps/integrations/providers/`.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, null=True,
        blank=True, related_name="integration_connections",
        verbose_name=_("client organization"),
        help_text=_("Blank for an agency-wide connection such as "
                    "RudderStack. Required for every advertising or "
                    "analytics provider, which reports on one client."),
    )
    provider = models.CharField(_("provider"), max_length=30,
                                choices=Provider.choices, db_index=True)
    display_name = models.CharField(
        _("name"), max_length=150, blank=True,
        help_text=_("How this connection is labelled in the dashboard, "
                    "e.g. “ABC Holdings — Meta Business Account”."),
    )
    external_account_id = models.CharField(
        _("external account ID"), max_length=200, blank=True,
        help_text=_("The ad account, property or workspace ID at the "
                    "provider. Not a secret — shown in the dashboard."),
    )

    #: Write-only in every outward-facing surface. Never add these to a
    #: serializer, a template context or an admin list_display.
    access_token = EncryptedTextField(_("access token"), blank=True)
    refresh_token = EncryptedTextField(_("refresh token"), blank=True)
    client_secret = EncryptedTextField(_("client secret"), blank=True)
    token_expires_at = models.DateTimeField(_("token expires"), null=True,
                                            blank=True)

    status = models.CharField(_("status"), max_length=30,
                              choices=ConnectionStatus.choices,
                              default=ConnectionStatus.NOT_CONFIGURED,
                              db_index=True)
    status_detail = models.CharField(
        _("status detail"), max_length=300, blank=True,
        help_text=_("A short, human reason for the current status. Never "
                    "a raw exception or stack trace — see "
                    "`services.record_sync_failure`."),
    )

    last_sync_at = models.DateTimeField(_("last sync attempt"), null=True,
                                        blank=True)
    last_successful_sync_at = models.DateTimeField(
        _("last successful sync"), null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="integration_connections_created",
        verbose_name=_("configured by"),
    )

    class Meta:
        verbose_name = _("integration connection")
        verbose_name_plural = _("integration connections")
        ordering = ["provider", "organization_id"]
        constraints = [
            # One connection per provider per client. A second Meta
            # account for the same client is a second ad account *within*
            # that connection's scope, not a second connection — keeping
            # that distinction means "which connection do I sync" is
            # never ambiguous.
            models.UniqueConstraint(
                fields=["organization", "provider"],
                name="one_connection_per_provider_per_client",
            ),
            # PostgreSQL treats every NULL as distinct, so the constraint
            # above would not stop two agency-wide RudderStack rows. This
            # catches that case specifically.
            models.UniqueConstraint(
                fields=["provider"],
                condition=models.Q(organization__isnull=True),
                name="one_agency_wide_connection_per_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "status"],
                         name="intconn_provider_status_idx"),
            models.Index(fields=["organization", "provider"],
                         name="intconn_org_provider_idx"),
        ]

    def __str__(self) -> str:
        if self.display_name:
            return self.display_name
        target = self.organization or "agency-wide"
        return f"{self.get_provider_display()} — {target}"

    def clean(self) -> None:
        super().clean()
        if self.provider in REQUIRES_ORGANIZATION and self.organization_id is None:
            raise ValidationError({
                "organization": _("This provider reports on one client "
                                  "and needs one chosen."),
            })
        if self.provider in FORBIDS_ORGANIZATION and self.organization_id is not None:
            raise ValidationError({
                "organization": _("This provider is agency-wide and does "
                                  "not belong to one client."),
            })

    # --- derived, for anything that renders this row ------------------

    @property
    def is_configured(self) -> bool:
        """Whether there is enough here to attempt a sync.

        Checked rather than assumed: a row can exist (somebody started
        setting it up) without holding a usable token yet.
        """
        return bool(self.external_account_id and self.access_token)

    @property
    def masked_account_id(self) -> str:
        """The account ID, for display — never the token itself."""
        value = self.external_account_id
        if not value:
            return ""
        if len(value) <= 4:
            return "••••"
        return f"····{value[-4:]}"

    @property
    def needs_attention(self) -> bool:
        return self.status in {ConnectionStatus.NEEDS_REAUTHORIZATION,
                               ConnectionStatus.ERROR}


class MappingStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    PAUSED = "paused", _("Paused")
    ENDED = "ended", _("Ended")


class ExternalCampaignReference(TimeStampedModel):
    """Which external campaign a client's campaign actually is.

    This is the join the whole data flow depends on: synced metrics
    arrive keyed by an external campaign ID, and this row is how they are
    attributed to the right client's campaign rather than left stranded.
    One internal campaign may run on more than one platform at once
    (Google and Meta together), so this is many-to-one, not one-to-one.
    """

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.CASCADE,
        related_name="external_references", verbose_name=_("campaign"),
    )
    connection = models.ForeignKey(
        IntegrationConnection, on_delete=models.CASCADE,
        related_name="campaign_references", verbose_name=_("connection"),
    )

    external_campaign_id = models.CharField(_("external campaign ID"),
                                             max_length=200)
    external_ad_set_id = models.CharField(_("external ad set ID"),
                                          max_length=200, blank=True)
    external_ad_id = models.CharField(_("external ad ID"), max_length=200,
                                      blank=True)
    external_post_id = models.CharField(
        _("external post ID"), max_length=200, blank=True,
        help_text=_("For a social provider reporting on one post."),
    )

    status = models.CharField(_("status"), max_length=20,
                              choices=MappingStatus.choices,
                              default=MappingStatus.ACTIVE, db_index=True)
    last_synced_at = models.DateTimeField(_("last synced"), null=True,
                                          blank=True)

    class Meta:
        verbose_name = _("external campaign mapping")
        verbose_name_plural = _("external campaign mappings")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["connection", "external_campaign_id"],
                name="one_mapping_per_external_campaign",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "status"],
                         name="extref_campaign_status_idx"),
        ]

    def __str__(self) -> str:
        provider = self.connection.get_provider_display()
        return f"{self.campaign_id} → {provider}:{self.external_campaign_id}"

    def clean(self) -> None:
        super().clean()
        if self.campaign_id and self.connection_id and \
                self.connection.organization_id is not None and \
                self.campaign.organization_id != self.connection.organization_id:
            raise ValidationError({
                "connection": _("That connection belongs to a different "
                                "client than the campaign."),
            })


class ProviderMetric(TimeStampedModel):
    """One provider-specific number a sync reported, that the normalized
    tables (`apps.paid_ads.DailyAdMetric` and its equivalents) have no
    column for.

    The common metrics every platform roughly agrees on — spend, reach,
    clicks, conversions — get their own columns, because they are shared
    and every report needs them fast. Everything past that (Meta's
    thruplays, Google's quality score, a platform's own cost-per-result
    calculated its way) would mean adding a nullable column for every
    platform's own vocabulary to a table every other platform also
    writes to. This is the flexible side instead: one row per metric,
    keyed by whatever name the provider itself uses, read back only by
    an advanced detail view that already knows to ask for it by name.

    Organization-scoped by the campaign it reports on, not independently,
    since there is never a reason for a provider metric to exist without
    one.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE,
        related_name="provider_metrics", verbose_name=_("client organization"),
    )
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.CASCADE,
        related_name="provider_metrics", verbose_name=_("campaign"),
    )
    provider = models.CharField(_("provider"), max_length=30,
                                choices=Provider.choices, db_index=True)
    date = models.DateField(_("date"), db_index=True)
    metric_key = models.CharField(
        _("metric"), max_length=60,
        help_text=_("The provider's own name for this number, e.g. "
                    "“thruplays” or “quality_score”."),
    )
    numeric_value = models.DecimalField(_("value"), max_digits=20,
                                        decimal_places=4)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("provider metric")
        verbose_name_plural = _("provider metrics")
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "provider", "date", "metric_key"],
                name="one_provider_metric_per_key_per_day",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "provider", "date"],
                         name="provmetric_org_prov_date_idx"),
            models.Index(fields=["campaign", "date"],
                         name="provmetric_campaign_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.campaign_id}: {self.metric_key}={self.numeric_value} on {self.date}"

    def clean(self) -> None:
        super().clean()
        if self.campaign_id and self.organization_id and \
                self.campaign.organization_id != self.organization_id:
            raise ValidationError({
                "campaign": _("That campaign belongs to a different "
                              "client."),
            })


class SyncStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    RUNNING = "running", _("Running")
    SUCCESS = "success", _("Success")
    PARTIAL = "partial", _("Partial")
    FAILED = "failed", _("Failed")
    SKIPPED = "skipped", _("Skipped — not configured")


class AnalyticsSyncRun(TimeStampedModel):
    """One attempt to pull data from one provider.

    The record that makes a failed sync honest rather than silent: the
    client dashboard falls back to whatever was last stored, admin gets
    an in-app notification, and this row is where "what actually
    happened" lives for whoever investigates later. Never deleted.
    """

    provider = models.CharField(_("provider"), max_length=30,
                                choices=Provider.choices, db_index=True)
    connection = models.ForeignKey(
        IntegrationConnection, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="sync_runs", verbose_name=_("connection"),
    )
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.SET_NULL, null=True,
        blank=True, related_name="analytics_sync_runs",
        verbose_name=_("client organization"),
    )

    status = models.CharField(_("status"), max_length=20,
                              choices=SyncStatus.choices,
                              default=SyncStatus.PENDING, db_index=True)
    started_at = models.DateTimeField(_("started"), auto_now_add=True)
    finished_at = models.DateTimeField(_("finished"), null=True, blank=True)

    records_received = models.PositiveIntegerField(_("records received"),
                                                    default=0)
    records_created = models.PositiveIntegerField(_("records created"),
                                                   default=0)
    records_updated = models.PositiveIntegerField(_("records updated"),
                                                   default=0)

    #: A sentence, not a traceback. Shown to admin; never to a client.
    error_summary = models.CharField(_("error summary"), max_length=300,
                                     blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="triggered_sync_runs",
        verbose_name=_("triggered by"),
        help_text=_("Blank for a scheduled run."),
    )

    class Meta:
        verbose_name = _("analytics sync run")
        verbose_name_plural = _("analytics sync runs")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["provider", "-started_at"],
                         name="syncrun_provider_started_idx"),
            models.Index(fields=["organization", "-started_at"],
                         name="syncrun_org_started_idx"),
            models.Index(fields=["status"], name="syncrun_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()} sync, {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class ProviderCredential(TimeStampedModel):
    """One piece of app-level credential for one provider.

    Not a client's connection — see `IntegrationConnection` for that.
    This is the developer-console side: the Meta App ID and secret, a
    Google Ads developer token, a LinkedIn client ID — the thing one
    app registration gets an agency, shared by every client's
    connection to that provider. Every adapter's `validate_connection`
    reads these instead of a hard-coded Django setting, so they can be
    entered from the dashboard (`/staff/integrations/<provider>/`)
    rather than requiring a redeploy with new environment variables.

    `key` is not a closed choice because it varies by provider — Meta
    needs `app_id` and `app_secret`; Google Ads needs a single
    `developer_token`; GA4 needs a `service_account_json`. See
    `apps.integrations.credentials.FIELDS_FOR_PROVIDER` for the actual
    set each provider's admin page asks for.
    """

    provider = models.CharField(_("provider"), max_length=30,
                                choices=Provider.choices, db_index=True)
    key = models.CharField(_("credential"), max_length=60)
    value = EncryptedTextField(_("value"), blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name="+", verbose_name=_("updated by"),
    )

    class Meta:
        verbose_name = _("provider credential")
        verbose_name_plural = _("provider credentials")
        ordering = ["provider", "key"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "key"],
                                    name="one_credential_per_provider_key"),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()}: {self.key}"
