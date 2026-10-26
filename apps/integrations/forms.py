"""Forms for configuring integration connections.

There is no OAuth flow in this version — see `docs/ANALYTICS.md` for
why. Configuring a connection means typing in the account ID and a token
obtained from the provider's own developer console, which is why every
secret field is a password-style textarea and never pre-filled with the
current value: showing a masked version back is enough confirmation that
something is stored, and retyping it is the honest way to change it.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledForm
from apps.integrations.credentials import fields_for
from apps.integrations.models import Provider


class ConnectionForm(StyledForm):
    display_name = forms.CharField(
        label=_("Name"), max_length=150, required=False,
        help_text=_("How this connection is labelled here, e.g. “ABC "
                    "Holdings — Meta Business Account”."),
    )
    external_account_id = forms.CharField(
        label=_("Account / property ID"), max_length=200, required=False,
        help_text=_("From the provider's own dashboard. Not secret."),
    )
    access_token = forms.CharField(
        label=_("Access token"), required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Leave blank to keep the one already stored."),
    )
    refresh_token = forms.CharField(
        label=_("Refresh token"), required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean(self) -> dict:
        cleaned = super().clean()
        # Blank means "unchanged", not "clear it" — so a blank token
        # field is simply not passed on to the service layer, which only
        # updates the fields it is given.
        for field in ("access_token", "refresh_token"):
            if not cleaned.get(field):
                cleaned.pop(field, None)
        return cleaned


class ProviderCredentialForm(StyledForm):
    """The app-level credential fields for one provider — a Meta App ID
    and secret, a Google Ads developer token, and so on.

    Built dynamically from `apps.integrations.credentials.fields_for`
    rather than one form class per provider: the shape differs (Meta
    needs two fields, Google Ads needs one), and a dictionary entry
    there should be the only thing a sixth provider needs to add here.
    """

    def __init__(self, *args, provider: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for field in fields_for(provider):
            self.fields[field.key] = forms.CharField(
                label=field.label, required=False,
                help_text=field.help_text
                         + (" Leave blank to keep the one already stored."
                            if field.secret else ""),
                widget=(forms.Textarea(attrs={"rows": 2})
                       if field.secret else forms.TextInput()),
            )


class CampaignMappingForm(StyledForm):
    connection = forms.ModelChoiceField(label=_("Connection"), queryset=None)
    external_campaign_id = forms.CharField(
        label=_("External campaign ID"), max_length=200,
        help_text=_("Copied from the provider's own ads manager. Typed "
                    "in, not looked up — there is no live campaign "
                    "picker in this version."),
    )
    external_ad_set_id = forms.CharField(label=_("Ad set / ad group ID"),
                                         max_length=200, required=False)
    external_ad_id = forms.CharField(label=_("Ad ID"), max_length=200,
                                     required=False)

    def __init__(self, *args, organization=None, **kwargs) -> None:  # noqa: ANN001
        super().__init__(*args, **kwargs)
        from apps.integrations.models import IntegrationConnection

        queryset = IntegrationConnection.objects.none()
        if organization is not None:
            from django.db.models import Q

            queryset = IntegrationConnection.objects.filter(
                Q(organization=organization) | Q(organization__isnull=True),
            ).order_by("provider")
        self.fields["connection"].queryset = queryset


class SyncNowForm(StyledForm):
    provider = forms.ChoiceField(label=_("Provider"), choices=Provider.choices)
    days = forms.IntegerField(label=_("Days to pull"), initial=7, min_value=1,
                              max_value=90)
