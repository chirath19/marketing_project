"""The LinkedIn Marketing API adapter.

`Provider.LINKEDIN_ADS` already existed in the closed provider list
before this adapter did — declared as a client-scoped advertising
provider but with nowhere for a sync to actually route, which meant
`get_adapter("linkedin_ads")` quietly returned `None`, the same answer
RudderStack gives for having no pull adapter by design. That was
inaccurate for LinkedIn specifically: it is a real ads platform this
brief names, not an event router, so it gets the same honest treatment
as Meta and Google — an adapter that always reports
`ProviderNotConfigured` until real credentials exist, rather than an
adapter that does not exist.
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


class LinkedInAdsProvider(MarketingAnalyticsProvider):
    provider_key = "linkedin_ads"

    def validate_connection(self, connection) -> bool:  # noqa: ANN001
        if not credentials.get(self.provider_key, "client_id") or not credentials.get(
            self.provider_key, "client_secret"
        ):
            raise ProviderNotConfigured(
                "No LinkedIn client ID and secret are configured yet — "
                "add them from this provider's own page in Integrations, "
                "so the platform has a way to exchange a LinkedIn access "
                "token."
            )
        if not connection.is_configured:
            raise ProviderNotConfigured(
                f"{connection} has no sponsored account ID or access "
                "token yet."
            )
        return True

    def fetch_accounts(self, connection) -> list[ExternalAccount]:  # noqa: ANN001
        # Would call GET /adAccounts with the stored access token.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_campaigns(self, connection) -> list[ExternalCampaign]:  # noqa: ANN001
        # Would call GET /adAccounts/{id}/adCampaigns.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_metrics(self, connection, *, external_campaign_id: str,  # noqa: ANN001
                      start: date, end: date) -> list[NormalizedMetrics]:
        # Would call the Ad Analytics finder with pivot CAMPAIGN,
        # timeGranularity DAILY, fields impressions,clicks,costInUsd,
        # videoViews,oneClickLeads.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured
