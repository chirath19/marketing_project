"""The TikTok Marketing API adapter.

The same shape as every other provider adapter in this package, and the
same honesty: no TikTok app ID or secret is configured anywhere in this
environment, so `validate_connection` always raises. The call that would
follow is documented, not written — `GET /report/integrated/get/` on the
Reporting API, `dimensions=["campaign_id", "stat_time_day"]`, `metrics=[
"spend", "impressions", "clicks", "reach", "video_watched_2s",
"result", "conversion"]`.
"""

from __future__ import annotations

from datetime import date

from apps.integrations import credentials
from apps.integrations.providers.base import (
    ExternalAccount,
    ExternalCampaign,
    MarketingAnalyticsProvider,
    NormalizedMetrics,
    ProviderNotConfigured,
)


class TikTokAdsProvider(MarketingAnalyticsProvider):
    provider_key = "tiktok_ads"

    def validate_connection(self, connection) -> bool:  # noqa: ANN001
        if not credentials.get(self.provider_key, "app_id") or not credentials.get(
            self.provider_key, "app_secret"
        ):
            raise ProviderNotConfigured(
                "No TikTok App ID and secret are configured yet — add "
                "them from this provider's own page in Integrations, so "
                "the platform has a way to exchange a TikTok access "
                "token."
            )
        if not connection.is_configured:
            raise ProviderNotConfigured(
                f"{connection} has no advertiser ID or access token yet."
            )
        return True

    def fetch_accounts(self, connection) -> list[ExternalAccount]:  # noqa: ANN001
        # Would call GET /oauth2/advertiser/get/ with the access token.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_campaigns(self, connection) -> list[ExternalCampaign]:  # noqa: ANN001
        # Would call GET /campaign/get/?advertiser_id=... .
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_metrics(self, connection, *, external_campaign_id: str,  # noqa: ANN001
                      start: date, end: date) -> list[NormalizedMetrics]:
        # Would call GET /report/integrated/get/ with data_level
        # "AUCTION_CAMPAIGN", dimensions ["campaign_id", "stat_time_day"].
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured
