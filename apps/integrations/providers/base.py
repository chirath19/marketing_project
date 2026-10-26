"""The interface every provider adapter implements.

Five methods, deliberately small. `sync()` is the only one the
management commands call; the other four exist because a sync is made of
four distinct, independently testable steps, and collapsing them into
one method would mean a provider that only needed to override one step
having to reimplement all four.

An adapter never touches the database directly — it returns plain data
(`NormalizedMetrics`), and `apps.integrations.services.run_sync` is what
writes rows. That split is what lets `sync()` be tested against a fake
adapter with no PostgreSQL in the loop at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


class ProviderNotConfigured(Exception):
    """Raised when a sync is attempted with no usable credentials.

    Caught exactly once, by `services.run_sync`, which turns it into an
    `AnalyticsSyncRun` with status `skipped` rather than letting it
    propagate — a management command run from cron must never crash the
    whole invocation because one client's Meta token was never entered.
    """


@dataclass(frozen=True, slots=True)
class ExternalAccount:
    """One ad account, property or page the connection can see."""

    external_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ExternalCampaign:
    """One campaign at the provider, before it is mapped to one of ours."""

    external_id: str
    name: str
    objective: str = ""


@dataclass(frozen=True, slots=True)
class NormalizedMetrics:
    """One external campaign's performance for one day, in shared units.

    This is the shape every adapter must produce regardless of what the
    provider itself calls its fields — Meta's "link_clicks" and Google
    Ads' "clicks" both become `clicks` here, which is what lets the
    client dashboard show one table for every platform. Monetary fields
    are `Decimal`-ready strings; the caller converts, so this dataclass
    carries no Django dependency.
    """

    external_campaign_id: str
    date: date
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    link_clicks: int = 0
    landing_page_views: int = 0
    engagements: int = 0
    video_views: int = 0
    spend: str = "0"
    leads: int = 0
    conversions: int = 0
    revenue: str = "0"
    currency: str = ""
    #: Anything the provider reports that the shared shape above has no
    #: field for — frequency, CPM as the provider itself calculated it,
    #: a platform-specific quality score. Kept rather than discarded, and
    #: read back out through `ProviderMetric` for an advanced detail view
    #: rather than forced into the normalized table.
    extra: dict = field(default_factory=dict)


class MarketingAnalyticsProvider(ABC):
    """One external advertising or analytics platform.

    `provider_key` must match a `apps.integrations.models.Provider`
    value — `get_adapter` depends on it to route a connection to the
    adapter that understands it.
    """

    provider_key: str

    @abstractmethod
    def validate_connection(self, connection) -> bool:  # noqa: ANN001
        """Whether `connection` holds credentials this adapter can use.

        Checked before every other call. Raises `ProviderNotConfigured`
        rather than returning `False` when it fails, so the caller gets
        one exception type to catch rather than a boolean it still has
        to turn into an error message.
        """

    @abstractmethod
    def fetch_accounts(self, connection) -> list[ExternalAccount]:  # noqa: ANN001
        """The accounts this connection's credentials can see."""

    @abstractmethod
    def fetch_campaigns(self, connection) -> list[ExternalCampaign]:  # noqa: ANN001
        """The campaigns running under the connected account."""

    @abstractmethod
    def fetch_metrics(self, connection, *, external_campaign_id: str,  # noqa: ANN001
                      start: date, end: date) -> list[NormalizedMetrics]:
        """Raw daily metrics for one external campaign, over a range.

        "Raw" in the sense of "as this provider reports them" — may
        already be close to normalized, may need real unit conversion;
        `normalize_metrics` is where that conversion is guaranteed to
        have happened.
        """

    def normalize_metrics(self, raw: list[NormalizedMetrics]) -> list[NormalizedMetrics]:
        """Hook for provider-specific conversion.

        The base implementation is the identity function: a provider
        whose `fetch_metrics` already returns `NormalizedMetrics` in
        shared units needs nothing more. A provider that reports, say,
        spend in the account's minor currency unit overrides this to
        divide by 100 before anything is written.
        """
        return raw

    def sync(self, connection, *, start: date, end: date):  # noqa: ANN001, ANN201
        """Pull and normalize one connection's metrics for a date range.

        The only method `apps.integrations.services.run_sync` calls.
        Raises `ProviderNotConfigured` if `validate_connection` does —
        deliberately not caught here, so the caller decides what an
        unconfigured provider means for the `AnalyticsSyncRun` it is
        writing.
        """
        self.validate_connection(connection)

        campaigns = self.fetch_campaigns(connection)
        results: list[NormalizedMetrics] = []
        for campaign in campaigns:
            raw = self.fetch_metrics(
                connection, external_campaign_id=campaign.external_id,
                start=start, end=end,
            )
            results.extend(self.normalize_metrics(raw))
        return results
