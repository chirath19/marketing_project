"""The Meta Marketing API adapter.

Not the Meta Pixel. The pixel reports website events *to* Meta, for ad
targeting and measurement on Meta's side; this adapter reads advertising
*results* *from* Meta, which is the only source the brief permits for a
client's Meta Ads performance. The two are never substituted for each
other anywhere in this codebase.

No request is made from this module in the current environment: there is
no Meta app ID, app secret or long-lived system-user token configured
anywhere in settings, so `validate_connection` always raises. The HTTP
call that would follow (`GET /act_{id}/insights` on the Marketing API,
`time_increment=1` for daily rows) is documented here rather than
written, because writing it against credentials nobody has would be
untested code masquerading as a working integration.
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


class MetaAdsProvider(MarketingAnalyticsProvider):
    provider_key = "meta_ads"

    def validate_connection(self, connection) -> bool:  # noqa: ANN001
        if not credentials.get(self.provider_key, "app_id") or not credentials.get(
            self.provider_key, "app_secret"
        ):
            raise ProviderNotConfigured(
                "No Meta App ID and secret are configured yet — add them "
                "from this provider's own page in Integrations, so the "
                "platform has a way to exchange a Meta access token."
            )
        if not connection.is_configured:
            raise ProviderNotConfigured(
                f"{connection} has no ad account ID or access token yet."
            )
        return True

    def fetch_accounts(self, connection) -> list[ExternalAccount]:  # noqa: ANN001
        # Would call GET /me/adaccounts with the stored access token.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_campaigns(self, connection) -> list[ExternalCampaign]:  # noqa: ANN001
        # Would call GET /act_{account_id}/campaigns?fields=id,name,objective.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured

    def fetch_metrics(self, connection, *, external_campaign_id: str,  # noqa: ANN001
                      start: date, end: date) -> list[NormalizedMetrics]:
        # Would call GET /{campaign_id}/insights with time_increment=1,
        # fields=impressions,reach,clicks,inline_link_clicks,spend,
        # actions,action_values, time_range={since,until}.
        self.validate_connection(connection)
        return []  # pragma: no cover - unreachable while unconfigured
