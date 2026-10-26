"""Provider adapters: the only code allowed to know a provider exists.

A view, a selector or a service function never imports `requests` or a
vendor SDK directly, and never builds a Meta or Google URL. Every call
out to an external system goes through one of these adapters, and every
adapter speaks the same four-method interface
(`apps.integrations.providers.base.MarketingAnalyticsProvider`) so the
sync layer that drives them does not care which provider it is talking
to.

`get_adapter(provider)` is the one lookup everything else should use —
it is what keeps a new provider a one-line addition here rather than a
search-and-replace through the sync service.
"""

from __future__ import annotations

from apps.integrations.models import Provider
from apps.integrations.providers.base import MarketingAnalyticsProvider, ProviderNotConfigured
from apps.integrations.providers.ga4 import GoogleAnalyticsProvider
from apps.integrations.providers.google_ads import GoogleAdsProvider
from apps.integrations.providers.linkedin_ads import LinkedInAdsProvider
from apps.integrations.providers.meta_ads import MetaAdsProvider
from apps.integrations.providers.search_console import SearchConsoleProvider
from apps.integrations.providers.tiktok_ads import TikTokAdsProvider

_ADAPTERS: dict[str, type[MarketingAnalyticsProvider]] = {
    Provider.META_ADS: MetaAdsProvider,
    Provider.GOOGLE_ADS: GoogleAdsProvider,
    Provider.GOOGLE_ANALYTICS: GoogleAnalyticsProvider,
    Provider.GOOGLE_SEARCH_CONSOLE: SearchConsoleProvider,
    Provider.LINKEDIN_ADS: LinkedInAdsProvider,
    Provider.TIKTOK_ADS: TikTokAdsProvider,
}


def get_adapter(provider: str) -> MarketingAnalyticsProvider | None:
    """The adapter for a provider, or `None` if none is registered.

    `None` rather than a `KeyError` — RudderStack is a real, valid
    provider with no analytics-pull adapter (it only ever routes events
    outward), and the caller deciding what that means is more honest
    than this module guessing.
    """
    adapter_class = _ADAPTERS.get(provider)
    return adapter_class() if adapter_class else None


__all__ = ["MarketingAnalyticsProvider", "ProviderNotConfigured", "get_adapter"]
