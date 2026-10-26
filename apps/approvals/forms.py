from django import forms

from apps.approvals import selectors
from apps.approvals.models import ApprovalRequest
from apps.core.forms import StyledForm


class RequestForm(StyledForm):
    campaign = forms.ModelChoiceField(queryset=None)
    title = forms.CharField(max_length=200)
    description = forms.CharField(
        required=False,
        widget=forms.Textarea,
        help_text="Everything here is shared with this client's authorized members.",
    )

    def __init__(self, *args, actor, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campaign"].queryset = selectors.campaigns_for(actor, organization)


class FilterForm(StyledForm):
    status = forms.ChoiceField(
        choices=[("", "All statuses"), *ApprovalRequest.Status.choices], required=False
    )
    search = forms.CharField(required=False, max_length=200, label="Search titles")


class DecisionForm(StyledForm):
    decision = forms.ChoiceField(
        choices=[
            ("approved", "Approve"),
            ("changes_requested", "Request changes"),
            ("rejected", "Reject"),
        ]
    )
    response = forms.CharField(
        required=False,
        max_length=5000,
        widget=forms.Textarea,
        label="Client response",
        help_text="Explain requested changes or a rejection.",
    )


class CommentForm(StyledForm):
    body = forms.CharField(
        max_length=5000,
        widget=forms.Textarea,
        label="Comment",
        help_text="Shared with the client and authorized staff.",
    )


class CancelForm(StyledForm):
    reason = forms.CharField(max_length=5000, widget=forms.Textarea)
