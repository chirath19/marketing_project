"""The one date-range filter every analytics page renders the same way.

A thin `forms.Form` around `apps.analytics.dateranges` — resolving the
chosen preset into a concrete `DateRange` is still `dateranges.resolve`'s
job; this only turns a query string into the three values that function
needs; see section 44's instruction not to build a second filter UI per
page.
"""

from __future__ import annotations

from django import forms

from apps.analytics import dateranges
from apps.core.forms import StyledForm


class DateRangeForm(StyledForm):
    range = forms.ChoiceField(
        label="Period", choices=dateranges.PRESET_CHOICES, required=False,
        initial=dateranges.DEFAULT_PRESET,
    )
    start = forms.DateField(label="From", required=False,
                            widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="Through", required=False,
                          widget=forms.DateInput(attrs={"type": "date"}))

    #: Overridden by `CampaignDateRangeForm` to offer "Campaign
    #: lifetime" too. Kept as a class attribute rather than duplicating
    #: the whole form, since the only difference is which choices the
    #: `range` field offers.
    choices = dateranges.PRESET_CHOICES

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["range"].choices = self.choices

    def resolve(self, **kwargs) -> dateranges.DateRange:
        """The chosen period, resolved — call after `is_valid()`."""
        data = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return dateranges.resolve(
            data.get("range") or dateranges.DEFAULT_PRESET,
            custom_start=data.get("start"), custom_end=data.get("end"),
            **kwargs,
        )


class CampaignDateRangeForm(DateRangeForm):
    """The same filter, with "Campaign lifetime" added — section 20."""

    choices = dateranges.CAMPAIGN_PRESET_CHOICES

    def resolve_for(self, campaign, **kwargs) -> dateranges.DateRange:
        data = self.cleaned_data if self.is_bound and self.is_valid() else {}
        return dateranges.resolve_for_campaign(
            data.get("range") or dateranges.DEFAULT_PRESET, campaign,
            custom_start=data.get("start"), custom_end=data.get("end"),
            **kwargs,
        )
