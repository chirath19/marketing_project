"""Scoped form choices; writes always pass through the service layer."""

from django import forms
from django.utils import timezone

from apps.core.forms import StyledForm, StyledModelForm
from apps.social import selectors
from apps.social.models import (
    METRICS,
    ContentItem,
    CreatorPartnership,
    SocialChannel,
    SocialDeliverable,
    SocialMetric,
)

DATE = forms.DateInput(attrs={"type": "date"})
DATETIME = forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})


class FilterForm(StyledForm):
    start = forms.DateField(required=False, label="From", widget=DATE)
    end = forms.DateField(required=False, label="Through", widget=DATE)
    campaign = forms.ModelChoiceField(queryset=None, required=False, empty_label="All campaigns")
    channel = forms.ModelChoiceField(queryset=None, required=False, empty_label="All channels")
    kind = forms.ChoiceField(
        choices=[("", "All formats"), *ContentItem.Kind.choices], required=False
    )
    status = forms.ChoiceField(
        choices=[("", "All statuses"), *ContentItem.Status.choices], required=False
    )

    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campaign"].queryset = selectors.campaigns_for(actor, organization)
        self.fields["channel"].queryset = selectors.channels_for(actor, organization)

    def clean(self):
        values = super().clean()
        if values.get("start") and values.get("end") and values["end"] < values["start"]:
            self.add_error("end", "Choose an end date on or after the start.")
        return values


class ScopedForm(StyledModelForm):
    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization = organization
        for field, selector in (
            ("campaign", selectors.campaigns_for),
            ("channel", selectors.channels_for),
            ("partnership", selectors.partnerships_for),
        ):
            if field in self.fields:
                self.fields[field].queryset = selector(actor, organization)


class ChannelForm(ScopedForm):
    class Meta:
        model = SocialChannel
        fields = ["name", "platform", "handle", "profile_url", "is_active"]


class PartnershipForm(ScopedForm):
    class Meta:
        model = CreatorPartnership
        fields = [
            "campaign",
            "creator_name",
            "platform",
            "profile_url",
            "brief",
            "internal_notes",
            "status",
            "due_on",
            "client_visible",
        ]
        widgets = {"due_on": DATE}


class ContentForm(ScopedForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = ContentItem
        fields = [
            "campaign",
            "channel",
            "partnership",
            "title",
            "kind",
            "caption",
            "scheduled_at",
            "client_visible",
            "internal_notes",
        ]
        widgets = {"scheduled_at": DATETIME}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expected_revision"].initial = self.instance.revision
        self.fields[
            "scheduled_at"
        ].help_text = f"Planning only. Enter time in {timezone.get_current_timezone_name()}."
        if not self.instance._state.adding:
            for field in ("campaign", "channel", "partnership"):
                self.fields[field].disabled = True


class DeliverableForm(ScopedForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = SocialDeliverable
        fields = [
            "title",
            "description",
            "asset_url",
            "due_on",
            "client_visible",
            "approval_required",
        ]
        widgets = {"due_on": DATE}

    def __init__(self, *args, content, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.content = content
        self.fields["expected_revision"].initial = self.instance.revision


class StatusForm(StyledForm):
    status = forms.ChoiceField(choices=ContentItem.Status.choices)
    published_at = forms.DateTimeField(required=False, widget=DATETIME)
    published_url = forms.URLField(
        required=False, help_text="The public URL of the manually published post."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            "published_at"
        ].help_text = f"Actual publication time in {timezone.get_current_timezone_name()}."


class MetricForm(ScopedForm):
    class Meta:
        model = SocialMetric
        fields = ["date", *METRICS, "source"]
        widgets = {"date": DATE}

    def __init__(self, *args, content, actor, **kwargs):
        super().__init__(*args, actor=actor, **kwargs)
        self.instance.content = content
        self.instance.recorded_by = actor
        self.fields["date"].initial = timezone.localdate

    def validate_constraints(self):
        # The service locks the parent and authorizes correction of an existing day.
        pass


class DecisionForm(StyledForm):
    decision = forms.ChoiceField(
        choices=[
            ("approved", "Approve"),
            ("changes_requested", "Request changes"),
            ("rejected", "Reject"),
        ]
    )
    feedback = forms.CharField(required=False, max_length=5000, widget=forms.Textarea)
