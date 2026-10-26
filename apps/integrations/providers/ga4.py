"""The GA4 Data API adapter — reporting, not tracking.

GA4 has two entirely separate jobs in this platform, and this module is
only the second one:

* **Tracking** happens client-side, in a visitor's browser, once they
  consent — see `apps/tracking`. It is a `gtag()` call that sends events
  to Google's servers. Nothing in this repository is involved beyond
  rendering the snippet.
* **Reporting** is this adapter: the GA4 Data API, called server-side
  with a service-account credential, to pull aggregated numbers *back*
  into PostgreSQL so the dashboard never has to call Google on a page
  load.

Installing the tracking snippet does **not** populate this adapter.
A GA4 property has to be connected separately — a service-account key
granted Viewer access on the property — before any report can be
fetched, which is the distinction `validate_connection` exists to
enforce.
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


class GoogleAnalyticsProvider(MarketingAnalyticsProvider):
    provider_key = "google_analytics"

    def validate_connection(self, connection) -> bool:  # noqa: ANN001
        if not credentials.get(self.provider_key, "service_account_json"):
            raise ProviderNotConfigured(
                "No GA4 service-account credential is configured yet — "
                "add one from this provider's own page in Integrations, "
                "so report requests can be authenticated."
            )
        if not connection.is_configured:
            raise ProviderNotConfigured(
                f"{connection} has no GA4 property ID recorded yet."
            )
        return True

    def fetch_accounts(self, connection) -> list[ExternalAccount]:  # noqa: ANN001
        # Would call the Admin API's AccountSummaries.list.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_campaigns(self, connection) -> list[ExternalCampaign]:  # noqa: ANN001
        """GA4 has no campaign objects of its own.

        It reports *sessions tagged with* a campaign name (UTM
        parameters or a Google Ads link), so this returns nothing — a
        GA4 connection contributes website metrics, not campaign rows.
        The sync service knows to treat this provider's `sync()`
        differently: see `apps.integrations.services.run_sync`.
        """
        self.validate_connection(connection)
        return []

    def fetch_metrics(self, connection, *, external_campaign_id: str,  # noqa: ANN001
                      start: date, end: date) -> list[NormalizedMetrics]:
        # Would call runReport on the Data API with dimensions=[date],
        # metrics=[activeUsers, sessions, screenPageViews, conversions].
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_site_metrics(self, connection, *, start: date, end: date) -> dict:  # noqa: ANN001
        """Property-level totals, for the agency or client website view.

        The method the website analytics pages actually call — GA4 is
        reported per property, not per campaign, so this is the real
        entry point rather than `fetch_metrics`.
        """
        self.validate_connection(connection)
        return {}  # pragma: no cover - unreachable while unconfigured
