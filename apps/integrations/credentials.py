"""Which app-level credential fields each provider's admin page asks for.

One small registry, so adding a sixth provider's credential form is a
dictionary entry here, not a new form class and a new view branch. Every
field is read and written through `ProviderCredential` (one encrypted
row per `(provider, key)`); nothing here touches Django settings — that
is only ever a fallback, in `get()` below, for an operator who prefers
environment variables to the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.integrations.models import Provider


@dataclass(frozen=True, slots=True)
class CredentialField:
    key: str
    label: str
    #: Masked in the form and never pre-filled with the stored value —
    #: the same convention `ConnectionForm` already uses for tokens.
    secret: bool = True
    help_text: str = ""
    #: The environment variable this field falls back to when nothing
    #: has been entered in the dashboard yet. Existing Railway
    #: deployments that already set these keep working unchanged.
    settings_name: str = ""


FIELDS_FOR_PROVIDER: dict[str, list[CredentialField]] = {
    Provider.META_ADS: [
        CredentialField("app_id", "Meta App ID", secret=False,
                        settings_name="META_APP_ID",
                        help_text="From the app's dashboard at "
                                  "developers.facebook.com."),
        CredentialField("app_secret", "Meta App secret",
                        settings_name="META_APP_SECRET"),
    ],
    Provider.GOOGLE_ADS: [
        CredentialField("developer_token", "Google Ads developer token",
                        settings_name="GOOGLE_ADS_DEVELOPER_TOKEN",
                        help_text="Issued once per Google Ads manager "
                                  "account, separately from OAuth "
                                  "credentials."),
    ],
    Provider.GOOGLE_ANALYTICS: [
        CredentialField("service_account_json", "Service account JSON",
                        settings_name="GOOGLE_SERVICE_ACCOUNT_JSON",
                        help_text="The full JSON key file for a Google "
                                  "Cloud service account granted Viewer "
                                  "access on the GA4 property."),
    ],
    Provider.GOOGLE_SEARCH_CONSOLE: [
        CredentialField("service_account_json", "Service account JSON",
                        settings_name="GOOGLE_SERVICE_ACCOUNT_JSON",
                        help_text="Can be the same service account used "
                                  "for Google Analytics, if it also has "
                                  "Search Console access."),
    ],
    Provider.LINKEDIN_ADS: [
        CredentialField("client_id", "LinkedIn client ID", secret=False,
                        settings_name="LINKEDIN_CLIENT_ID"),
        CredentialField("client_secret", "LinkedIn client secret",
                        settings_name="LINKEDIN_CLIENT_SECRET"),
    ],
    Provider.TIKTOK_ADS: [
        CredentialField("app_id", "TikTok App ID", secret=False,
                        settings_name="TIKTOK_APP_ID"),
        CredentialField("app_secret", "TikTok App secret",
                        settings_name="TIKTOK_APP_SECRET"),
    ],
}


def fields_for(provider: str) -> list[CredentialField]:
    """The credential fields this provider's admin page should show.

    Empty for RudderStack and anything else with no adapter — there is
    no app-level credential to ask for when there is nothing to
    authenticate against.
    """
    return FIELDS_FOR_PROVIDER.get(provider, [])


def get(provider: str, key: str, *, default: str = "") -> str:
    """One credential's current value — the dashboard row if one has
    been entered, otherwise the environment variable it falls back to.

    This is what every adapter's `validate_connection` calls instead of
    `getattr(settings, "...")` directly, so entering a credential from
    `/staff/integrations/<provider>/` takes effect immediately, with no
    redeploy.
    """
    from apps.integrations.models import ProviderCredential

    row = ProviderCredential.objects.filter(provider=provider, key=key).first()
    if row is not None and row.value:
        return row.value

    field = next((f for f in fields_for(provider) if f.key == key), None)
    if field is not None and field.settings_name:
        return getattr(settings, field.settings_name, default)
    return default
