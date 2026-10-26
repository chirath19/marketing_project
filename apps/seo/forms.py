"""Forms for the SEO workspace.

Every numeric field here is entered by a person or imported from a file
they exported. The help text says so, and says where to record the
source — because a figure with no provenance is one nobody can defend in
a client meeting six months later.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledForm
from apps.seo.models import (
    AuditStatus,
    BacklinkStatus,
    IssueSeverity,
    IssueStatus,
    TaskKind,
    TaskStatus,
)


class AuditForm(StyledForm):
    title = forms.CharField(
        label=_("Title"), max_length=200,
        help_text=_("For example, “Technical audit, March 2026”."),
    )
    site_url = forms.URLField(label=_("Site audited"), max_length=300,
                              required=False)
    performed_on = forms.DateField(
        label=_("Carried out"), widget=forms.DateInput(attrs={"type": "date"}),
    )

    health_score = forms.IntegerField(
        label=_("Technical health"), required=False, min_value=0, max_value=100,
        help_text=_("Out of 100, as you assessed it. Leave blank if this "
                    "audit did not measure it."),
    )
    pages_crawled = forms.IntegerField(label=_("Pages crawled"), required=False,
                                       min_value=0)
    score_source = forms.CharField(
        label=_("Where the figures came from"), max_length=200, required=False,
        help_text=_("The tool or method behind the numbers. Recorded so "
                    "nobody has to guess later."),
    )

    summary = forms.CharField(
        label=_("Summary for the client"), required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text=_("What the audit found, in plain language. The client "
                    "sees this once you deliver the audit — not before."),
    )
    internal_notes = forms.CharField(
        label=_("Internal notes"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Staff only. The client never sees this."),
    )

    field_order = ["title", "site_url", "performed_on", "health_score",
                   "pages_crawled", "score_source", "summary", "internal_notes"]

    @classmethod
    def for_audit(cls, audit, data=None):  # noqa: ANN001, ANN206
        return cls(data=data, initial={
            "title": audit.title, "site_url": audit.site_url,
            "performed_on": audit.performed_on,
            "health_score": audit.health_score,
            "pages_crawled": audit.pages_crawled,
            "score_source": audit.score_source,
            "summary": audit.summary, "internal_notes": audit.internal_notes,
        })


class IssueForm(StyledForm):
    title = forms.CharField(label=_("Issue"), max_length=250)
    severity = forms.ChoiceField(label=_("Severity"),
                                 choices=IssueSeverity.choices,
                                 initial=IssueSeverity.MEDIUM)
    status = forms.ChoiceField(label=_("Status"), choices=IssueStatus.choices,
                               initial=IssueStatus.OPEN)
    detail = forms.CharField(
        label=_("What is wrong"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    recommendation = forms.CharField(
        label=_("What to do"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Written so a developer can act on it."),
    )
    affected_urls = forms.CharField(
        label=_("Affected pages"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("One URL per line."),
    )
    pages_affected = forms.IntegerField(
        label=_("How many pages"), required=False, min_value=0,
        help_text=_("Where it is more than you would list."),
    )


class KeywordForm(StyledForm):
    term = forms.CharField(label=_("Search term"), max_length=200)
    target_url = forms.URLField(
        label=_("Target page"), max_length=300, required=False,
        help_text=_("The page you want to rank. Blank is fine — not having "
                    "decided is itself worth knowing."),
    )
    search_volume = forms.IntegerField(
        label=_("Monthly searches"), required=False, min_value=0,
        help_text=_("As reported by whichever tool you took it from. "
                    "Nothing here is fetched."),
    )
    difficulty = forms.IntegerField(label=_("Difficulty"), required=False,
                                    min_value=0, max_value=100)
    priority = forms.ChoiceField(
        label=_("Priority"),
        choices=[(1, _("1 — highest")), (2, _("2")), (3, _("3")), (4, _("4"))],
        initial=2,
    )


class PositionForm(StyledForm):
    """A single reading, typed in."""

    recorded_on = forms.DateField(
        label=_("Observed on"), widget=forms.DateInput(attrs={"type": "date"}),
    )
    position = forms.IntegerField(
        label=_("Position"), required=False, min_value=1, max_value=200,
        help_text=_("Leave blank for “not in the top 200”, which is "
                    "different from no reading at all."),
    )
    source = forms.CharField(
        label=_("Source"), max_length=120, required=False,
        help_text=_("Where this reading came from, so it can be traced."),
    )


class KeywordImportForm(StyledForm):
    """A CSV from whichever rank tracker the agency uses."""

    file = forms.FileField(
        label=_("CSV file"),
        help_text=_("A keyword column is required. Position, date, URL and "
                    "volume are read when present. Common column names from "
                    "the usual tools are understood."),
    )
    recorded_on = forms.DateField(
        label=_("Date for rows without one"), required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Defaults to today."),
    )
    source = forms.CharField(
        label=_("Source"), max_length=120, required=False,
        help_text=_("The tool this came from. Recorded against every "
                    "reading."),
    )

    def clean_file(self):  # noqa: ANN201
        uploaded = self.cleaned_data["file"]
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError(
                _("That file is larger than 5 MB. Export a narrower date "
                  "range.")
            )
        if not uploaded.name.lower().endswith(".csv"):
            raise forms.ValidationError(_("Upload a .csv file."))
        return uploaded


class TaskForm(StyledForm):
    title = forms.CharField(label=_("Task"), max_length=250)
    kind = forms.ChoiceField(label=_("Kind"), choices=TaskKind.choices,
                             initial=TaskKind.CONTENT)
    status = forms.ChoiceField(label=_("Status"), choices=TaskStatus.choices,
                               initial=TaskStatus.PLANNED)
    detail = forms.CharField(label=_("Detail"), required=False,
                             widget=forms.Textarea(attrs={"rows": 3}))
    client_summary = forms.CharField(
        label=_("Summary for the client"), max_length=300, required=False,
        help_text=_("Shown in their workspace. Leave blank to keep this "
                    "task internal."),
    )
    assigned_to = forms.ModelChoiceField(
        label=_("Assigned to"), queryset=None, required=False,
        empty_label=_("Nobody"),
    )
    due_on = forms.DateField(label=_("Due"), required=False,
                             widget=forms.DateInput(attrs={"type": "date"}))
    delivered_url = forms.URLField(
        label=_("Where it landed"), max_length=300, required=False,
        help_text=_("The published page or document. This is what makes a "
                    "finished task a deliverable."),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        from django.contrib.auth import get_user_model

        from apps.accounts.models import AccountStatus, UserType

        self.fields["assigned_to"].queryset = (
            get_user_model().objects
            .filter(status=AccountStatus.ACTIVE,
                    user_type__in=[UserType.STAFF, UserType.SUPER_ADMIN])
            .order_by("full_name", "email")
        )


class BacklinkForm(StyledForm):
    source_domain = forms.CharField(label=_("From"), max_length=200,
                                    help_text=_("The site linking to you."))
    source_url = forms.URLField(label=_("Link page"), max_length=500,
                                required=False)
    target_url = forms.URLField(label=_("Links to"), max_length=300,
                                required=False)
    anchor_text = forms.CharField(label=_("Anchor text"), max_length=250,
                                  required=False)
    status = forms.ChoiceField(label=_("Status"), choices=BacklinkStatus.choices,
                               initial=BacklinkStatus.PROSPECT)
    authority = forms.IntegerField(
        label=_("Authority"), required=False, min_value=0, max_value=100,
        help_text=_("Whatever authority metric you use. Not fetched."),
    )
    is_follow = forms.BooleanField(label=_("Followed link"), required=False,
                                   initial=True)
    contacted_on = forms.DateField(label=_("Contacted"), required=False,
                                   widget=forms.DateInput(attrs={"type": "date"}))
    went_live_on = forms.DateField(label=_("Went live"), required=False,
                                   widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(label=_("Internal notes"), required=False,
                            widget=forms.Textarea(attrs={"rows": 2}),
                            help_text=_("Staff only."))


class AuditStatusForm(StyledForm):
    status = forms.ChoiceField(label=_("Status"), choices=AuditStatus.choices)
