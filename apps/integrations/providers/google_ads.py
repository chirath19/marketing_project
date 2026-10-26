"""The Google Ads API adapter.

As with Meta, nothing here calls out: Google Ads requires a developer
token issued by Google per manager account, which this environment does
not have, in addition to OAuth client credentials. `validate_connection`
raises until one is configured in settings.

Google Ads reports spend and some bid values in **micros** (millionths
of the account currency unit) — the one provider-specific conversion
that genuinely cannot live in `fetch_metrics` without risking being
forgotten, so it is pinned here in `normalize_metrics` instead, where it
cannot be skipped.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.integrations import credentials
from apps.integrations.providers.base import (
    ExternalAccount,
    ExternalCampaign,
    MarketingAnalyticsProvider,
    NormalizedMetrics,
    ProviderNotConfigured,
)

MICROS_PER_UNIT = Decimal("1000000")


class GoogleAdsProvider(MarketingAnalyticsProvider):
    provider_key = "google_ads"

    def validate_connection(self, connection) -> bool:  # noqa: ANN001
        if not credentials.get(self.provider_key, "developer_token"):
            raise ProviderNotConfigured(
                "No Google Ads developer token is configured yet — add "
                "one from this provider's own page in Integrations. "
                "Google issues one per manager account, separately from "
                "OAuth credentials."
            )
        if not connection.is_configured:
            raise ProviderNotConfigured(
                f"{connection} has no customer ID or access token yet."
            )
        return True

    def fetch_accounts(self, connection) -> list[ExternalAccount]:  # noqa: ANN001
        # Would call CustomerService.ListAccessibleCustomers.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_campaigns(self, connection) -> list[ExternalCampaign]:  # noqa: ANN001
        # Would run a GAQL query against campaign.id, campaign.name,
        # campaign.advertising_channel_type via GoogleAdsService.Search.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_metrics(self, connection, *, external_campaign_id: str,  # noqa: ANN001
                      start: date, end: date) -> list[NormalizedMetrics]:
        # Would query campaign + metrics.{impressions,clicks,conversions,
        # cost_micros,conversions_value} segmented by segments.date.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def normalize_metrics(self, raw: list[NormalizedMetrics]) -> list[NormalizedMetrics]:
        """Convert cost and conversion-value micros to whole currency units."""
        from dataclasses import replace

        return [
            replace(
                row,
                spend=str(Decimal(row.spend) / MICROS_PER_UNIT),
                revenue=str(Decimal(row.revenue) / MICROS_PER_UNIT),
            )
            for row in raw
        ]
