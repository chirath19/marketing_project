"""Manual observations, bounded reporting filters and period goals."""

from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from apps.core.forms import StyledForm, StyledModelForm
from apps.paid_ads import selectors
from apps.paid_ads.models import DailyAdMetric, PaidAdsCampaignDetail, PaidAdsGoal, Platform


class PaidAdsCampaignDetailForm(StyledModelForm):
    """Platform and objective for one paid promotion.

    The form the campaign admin page's generic detail-edit slot
    resolves for `service_type="paid_ads"` — see
    `apps.campaigns.registry.detail_form_for`. Setting these is what
    makes the campaign's own performance page lead with the right KPIs
    (an awareness campaign with reach, a lead-gen one with CPL) instead
    of a one-size-fits-all list.
    """

    class Meta:
        model = PaidAdsCampaignDetail
        fields = ["platform", "objective"]


class FilterForm(StyledForm):
    start = forms.DateField(label="From", widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(label="Through", widget=forms.DateInput(attrs={"type": "date"}))
    platform = forms.ChoiceField(choices=[("", "All platforms"), *Platform.choices], required=False)
    campaign = forms.ModelChoiceField(queryset=None, required=False, empty_label="All campaigns")
    currency = forms.RegexField(
        regex=r"^[A-Z]{3}$",
        max_length=3,
        help_text="Currencies are reported separately; no conversion.",
    )

    def __init__(self, data=None, *, actor, organization, **kwargs):
        defaults = {
            "start": timezone.localdate() - timedelta(days=29),
            "end": timezone.localdate(),
            "currency": settings.SITE_DEFAULT_CURRENCY,
        }
        if data is not None:
            data = data.copy()
            for key, value in defaults.items():
                if not data.get(key):
                    data[key] = value
        super().__init__(data=data, initial=defaults, **kwargs)
        self.fields["campaign"].queryset = selectors.campaigns_for(actor, organization)

    def clean(self):
        values = super().clean()
        start, end = values.get("start"), values.get("end")
        if start and end:
            if end < start:
                self.add_error("end", "The end must be on or after the start.")
            elif (end - start).days > 365:
                self.add_error("end", "Choose at most 366 days per report.")
        return values


class MetricForm(StyledModelForm):
    class Meta:
        model = DailyAdMetric
        fields = [
            "date",
            "campaign",
            "platform",
            "spend",
            "impressions",
            "clicks",
            "leads",
            "conversions",
            "revenue",
            "reach",
            "link_clicks",
            "landing_page_views",
            "engagements",
            "video_views",
            "source",
        ]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}
        help_texts = {
            "reach": "Optional. Leave blank if this platform's export "
                    "does not report it.",
            "link_clicks": "Optional.",
            "landing_page_views": "Optional.",
            "engagements": "Optional.",
            "video_views": "Optional.",
        }

    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization = organization
        self.fields["campaign"].queryset = selectors.campaigns_for(actor, organization)
        self.fields["date"].initial = timezone.localdate

    def validate_constraints(self):
        # Daily uniqueness is handled by the authorized, locked service upsert.
        # All model constraints are checked there before persistence.
        pass


class GoalForm(StyledModelForm):
    class Meta:
        model = PaidAdsGoal
        fields = [
            "title",
            "metric",
            "target",
            "starts_on",
            "ends_on",
            "currency",
            "platform",
            "campaign",
            "is_active",
        ]
        widgets = {key: forms.DateInput(attrs={"type": "date"}) for key in ("starts_on", "ends_on")}

    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization = organization
        self.fields["campaign"].queryset = selectors.campaigns_for(actor, organization)
        self.fields["currency"].initial = settings.SITE_DEFAULT_CURRENCY


class ImportForm(StyledForm):
    file = forms.FileField(label="CSV file")
    source = forms.CharField(max_length=200, help_text="Source report and export date.")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Upload a CSV no larger than 5 MB.")
        if not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError("Upload a .csv file.")
        return uploaded
