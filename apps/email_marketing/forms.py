"""Manual agency-service forms. No recipient lists, sender credentials or send actions."""

from django import forms
from django.utils import timezone

from apps.core.forms import StyledForm, StyledModelForm
from apps.email_marketing import selectors
from apps.email_marketing.models import METRICS, EmailDeliverable, EmailMetric, EmailWorkItem
from apps.email_marketing.services import REPORT_FIELDS, TRANSITIONS

DATE = forms.DateInput(attrs={"type": "date"})
DATETIME = forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})


class FilterForm(StyledForm):
    start = forms.DateField(required=False, label="From", widget=DATE)
    end = forms.DateField(required=False, label="Through", widget=DATE)
    campaign = forms.ModelChoiceField(queryset=None, required=False, empty_label="All campaigns")
    kind = forms.ChoiceField(
        choices=[("", "All work types"), *EmailWorkItem.Kind.choices], required=False
    )
    status = forms.ChoiceField(
        choices=[("", "All statuses"), *EmailWorkItem.Status.choices], required=False
    )

    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campaign"].queryset = selectors.campaigns_for(actor, organization)

    def clean(self):
        values = super().clean()
        if values.get("start") and values.get("end") and values["end"] < values["start"]:
            self.add_error("end", "Choose an end date on or after the start.")
        return values


class WorkForm(StyledModelForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = EmailWorkItem
        fields = [
            "campaign",
            "name",
            "kind",
            "subject",
            "brief",
            "audience_description",
            "audience_size",
            "trigger_description",
            "scheduled_at",
            "client_visible",
            "result_summary",
            "internal_notes",
        ]
        widgets = {"scheduled_at": DATETIME}

    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization = organization
        self.fields["campaign"].queryset = selectors.campaigns_for(actor, organization)
        self.fields["expected_revision"].initial = self.instance.revision
        self.fields[
            "scheduled_at"
        ].help_text = f"Planning only. Enter time in {timezone.get_current_timezone_name()}."
        if not self.instance._state.adding:
            self.fields["campaign"].disabled = True
        if self.instance.executed_at or self.instance.status in {"completed", "cancelled"}:
            for key, field in self.fields.items():
                if key not in REPORT_FIELDS | {"expected_revision"}:
                    field.disabled = True

    def clean(self):
        values = super().clean()
        # Disabled fields are display-only. In particular, a datetime widget can
        # drop sub-second precision; do not turn a report edit into a creative edit.
        return {key: value for key, value in values.items() if not self.fields[key].disabled}


class DeliverableForm(StyledModelForm):
    expected_revision = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = EmailDeliverable
        fields = [
            "name",
            "description",
            "asset_url",
            "due_on",
            "client_visible",
            "approval_required",
        ]
        widgets = {"due_on": DATE}

    def __init__(self, *args, actor, organization, work, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization, self.instance.work = organization, work
        self.fields["expected_revision"].initial = self.instance.revision


class StatusForm(StyledForm):
    status = forms.ChoiceField(choices=[])
    executed_at = forms.DateTimeField(required=False, widget=DATETIME)
    execution_note = forms.CharField(
        required=False,
        max_length=250,
        help_text=(
            "External report or execution reference. Saving does not send or activate anything."
        ),
    )

    def __init__(self, *args, work, can_record_execution, **kwargs):
        super().__init__(*args, **kwargs)
        allowed = TRANSITIONS.get(work.status, set()).copy()
        if work.kind != "automation":
            allowed.discard("active")
        if not can_record_execution:
            allowed -= {"active", "completed"}
        self.fields["status"].choices = [
            (key, label) for key, label in EmailWorkItem.Status.choices if key in allowed
        ]
        self.fields[
            "executed_at"
        ].help_text = f"Actual external execution time in {timezone.get_current_timezone_name()}."
        if work.executed_at:
            self.fields["executed_at"].initial = work.executed_at
            self.fields["execution_note"].initial = work.execution_note
            self.fields["executed_at"].disabled = True
            self.fields["execution_note"].disabled = True


class MetricForm(StyledModelForm):
    class Meta:
        model = EmailMetric
        fields = ["date", *METRICS, "source", "result_summary"]
        widgets = {"date": DATE}

    def __init__(self, *args, actor, organization, work, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.organization, self.instance.work, self.instance.recorded_by = (
            organization,
            work,
            actor,
        )
        self.fields["date"].initial = timezone.localdate

    def validate_constraints(self):
        # Services lock the work and authorize replacing an existing observation.
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
