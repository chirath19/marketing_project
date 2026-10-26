"""Forms for creating and working campaigns.

One form for every service area. The fields that differ between an SEO
campaign and a paid one are the *detail* a service module attaches, not
the core — so this form does not branch on type, and the objective's
label is read from the registry rather than hard-coded.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.campaigns.models import Campaign, CampaignStatus
from apps.campaigns.registry import get_type, type_choices
from apps.core.forms import StyledForm


class CampaignForm(StyledForm):
    """Create a campaign, or correct one already running."""

    name = forms.CharField(label=_("Campaign name"), max_length=200)
    service_type = forms.ChoiceField(
        label=_("Service area"), choices=[],
        help_text=_("Which part of the client's workspace this appears in."),
    )
    subscription = forms.ModelChoiceField(
        label=_("Delivered under"), queryset=None, required=False,
        empty_label=_("Not linked to a service"),
        help_text=_("The client service this is part of. Leave blank only "
                    "where there genuinely is not one yet."),
    )

    objective = forms.CharField(
        label=_("Objective"), max_length=250, required=False,
        help_text=_("What success looks like for this campaign."),
    )
    description = forms.CharField(
        label=_("Description"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("What this is and why it is running. Staff only."),
    )

    budget = forms.DecimalField(
        label=_("Budget"), max_digits=12, decimal_places=2, required=False,
        min_value=0,
        help_text=_("Media or production budget. Not the fee — that lives "
                    "on the service."),
    )
    currency = forms.CharField(label=_("Currency"), max_length=3, required=False,
                               initial="USD")

    starts_on = forms.DateField(
        label=_("Starts"), required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Set automatically when you take it live, if blank."),
    )
    ends_on = forms.DateField(
        label=_("Ends"), required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Leave blank for ongoing work with no agreed end."),
    )

    client_summary = forms.CharField(
        label=_("Summary for the client"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Shown in their workspace. Write it as if they are "
                    "reading it, because they are."),
    )
    internal_notes = forms.CharField(
        label=_("Internal notes"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Staff only. The client never sees this."),
    )

    field_order = ["name", "service_type", "subscription", "objective",
                   "description", "budget", "currency", "starts_on",
                   "ends_on", "client_summary", "internal_notes"]

    def __init__(self, *args, organization=None, instance=None, **kwargs) -> None:  # noqa: ANN001
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.instance = instance

        self.fields["service_type"].choices = type_choices()

        # Only this client's services. Offering another client's would be
        # a validation error waiting to happen and a hint about who else
        # the agency works with.
        from apps.subscriptions.models import ClientSubscription

        queryset = ClientSubscription.objects.none()
        if organization is not None:
            queryset = (
                ClientSubscription.objects
                .filter(organization=organization)
                .select_related("service")
                .order_by("-status", "name")
            )
        self.fields["subscription"].queryset = queryset

        # The label the objective goes by depends on the area, so an SEO
        # campaign asks for target positions and a paid one for cost per
        # customer, from one form.
        chosen = (self.data.get("service_type")
                  or self.initial.get("service_type") or "")
        campaign_type = get_type(chosen)
        if campaign_type is not None:
            self.fields["objective"].label = campaign_type.goal_label

    def clean(self) -> dict:
        cleaned = super().clean()
        starts, ends = cleaned.get("starts_on"), cleaned.get("ends_on")
        subscription = cleaned.get("subscription")

        if starts and ends and ends < starts:
            self.add_error("ends_on", _("A campaign cannot end before it starts."))

        if subscription is not None and self.organization is not None \
                and subscription.organization_id != self.organization.pk:
            self.add_error("subscription",
                           _("That service belongs to a different client."))

        return cleaned

    @classmethod
    def for_campaign(cls, campaign: Campaign, data=None):  # noqa: ANN206
        return cls(
            data=data, organization=campaign.organization, instance=campaign,
            initial={
                "name": campaign.name,
                "service_type": campaign.service_type,
                "subscription": campaign.subscription_id,
                "objective": campaign.objective,
                "description": campaign.description,
                "budget": campaign.budget,
                "currency": campaign.currency,
                "starts_on": campaign.starts_on,
                "ends_on": campaign.ends_on,
                "client_summary": campaign.client_summary,
                "internal_notes": campaign.internal_notes,
            },
        )


class CampaignStatusForm(StyledForm):
    status = forms.ChoiceField(label=_("Move to"), choices=[])
    note = forms.CharField(
        label=_("Note"), required=False, max_length=250,
        help_text=_("Optional. Recorded in the history beside the change."),
    )

    def __init__(self, *args, campaign=None, **kwargs) -> None:  # noqa: ANN001
        super().__init__(*args, **kwargs)

        from apps.campaigns.services import ALLOWED_TRANSITIONS

        # Only the moves this campaign can actually make. Offering the
        # rest and refusing them afterwards teaches people to distrust
        # the form, and the service layer would refuse them anyway.
        allowed = ALLOWED_TRANSITIONS.get(getattr(campaign, "status", ""),
                                          frozenset())
        labels = dict(CampaignStatus.choices)
        self.fields["status"].choices = [
            (value, labels[value]) for value in CampaignStatus.values
            if value in allowed
        ]


class CampaignAssignForm(StyledForm):
    owner = forms.ModelChoiceField(
        label=_("Owner"), queryset=None, required=False,
        empty_label=_("Nobody"),
        help_text=_("The one person accountable for this campaign."),
    )
    assignees = forms.ModelMultipleChoiceField(
        label=_("Working on it"), queryset=None, required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Everyone else involved."),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        from django.contrib.auth import get_user_model

        from apps.accounts.models import AccountStatus, UserType

        staff = (
            get_user_model().objects
            .filter(status=AccountStatus.ACTIVE,
                    user_type__in=[UserType.STAFF, UserType.SUPER_ADMIN])
            .order_by("full_name", "email")
        )
        self.fields["owner"].queryset = staff
        self.fields["assignees"].queryset = staff


class CampaignNoteForm(StyledForm):
    body = forms.CharField(
        label=_("Note"), widget=forms.Textarea(attrs={"rows": 3}), max_length=4000,
    )
    share_with_client = forms.BooleanField(
        label=_("Show this to the client"), required=False,
        help_text=_("Off by default. An internal note is never shown in "
                    "their workspace."),
    )
