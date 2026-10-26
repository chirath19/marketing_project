"""The Google Search Console API adapter.

Reports organic search performance — queries, clicks, impressions,
average position — for a verified property. Like GA4, it needs a
service-account credential granted access in Search Console separately
from anything the agency website's own GTM/GA4 tags do. Not configured in
this environment; see `apps.integrations.providers.ga4` for the fuller
explanation of why that is the honest state to ship in.
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


class SearchConsoleProvider(MarketingAnalyticsProvider):
    provider_key = "google_search_console"

    def validate_connection(self, connection) -> bool:  # noqa: ANN001
        if not credentials.get(self.provider_key, "service_account_json"):
            raise ProviderNotConfigured(
                "No Search Console service-account credential is "
                "configured yet — add one from this provider's own "
                "page in Integrations."
            )
        if not connection.is_configured:
            raise ProviderNotConfigured(
                f"{connection} has no verified property recorded yet."
            )
        return True

    def fetch_accounts(self, connection) -> list[ExternalAccount]:  # noqa: ANN001
        # Would call sites.list.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_campaigns(self, connection) -> list[ExternalCampaign]:  # noqa: ANN001
        """Search Console has no campaigns either — see the GA4 adapter."""
        self.validate_connection(connection)
        return []

    def fetch_metrics(self, connection, *, external_campaign_id: str,  # noqa: ANN001
                      start: date, end: date) -> list[NormalizedMetrics]:
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_search_performance(self, connection, *, start: date,  # noqa: ANN001
                                 end: date) -> dict:
        """Clicks, impressions and average position for the property.

        Would call searchanalytics.query with
        dimensions=["date"], startDate/endDate set from the range.
        """
        self.validate_connection(connection)
        return {}  # pragma: no cover - unreachable while unconfigured
