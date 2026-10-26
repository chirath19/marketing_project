"""Organization forms.

Validation only. Every write goes through `services.py`, so these forms
never touch the database themselves — which is also why they are plain
forms rather than ModelForms: a ModelForm writes submitted values onto
its instance during validation, which quietly defeats a service that
compares old against new.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledForm
from apps.organizations.models import MemberRole, Organization


class OrganizationSetupForm(StyledForm):
    """Onboarding: the minimum needed to open a workspace.

    Only the name is required. Asking a new client for a full postal
    address before they have seen anything is how onboarding gets
    abandoned; the rest is filled in later on the settings page.
    """

    name = forms.CharField(
        label=_("Company name"), max_length=200,
        help_text=_("The name your workspace will be set up under."),
    )
    website = forms.URLField(label=_("Website"), max_length=255, required=False)
    phone = forms.CharField(label=_("Phone"), max_length=32, required=False)
    country = forms.CharField(label=_("Country"), max_length=100, required=False)

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError(_("Enter your company name."))
        return name


class OrganizationProfileForm(StyledForm):
    """The company's own details, editable by an owner or admin."""

    name = forms.CharField(label=_("Legal name"), max_length=200)
    display_name = forms.CharField(
        label=_("Display name"), max_length=200, required=False,
        help_text=_("Trading name, if it differs from the legal name."),
    )
    website = forms.URLField(label=_("Website"), max_length=255, required=False)
    email = forms.EmailField(
        label=_("General contact email"), required=False,
        help_text=_("A record of where to reach you. We do not send to it."),
    )
    phone = forms.CharField(label=_("Phone"), max_length=32, required=False)

    address_line1 = forms.CharField(label=_("Address line 1"), max_length=200,
                                    required=False)
    address_line2 = forms.CharField(label=_("Address line 2"), max_length=200,
                                    required=False)
    city = forms.CharField(label=_("City"), max_length=120, required=False)
    region = forms.CharField(label=_("State or region"), max_length=120,
                             required=False)
    postal_code = forms.CharField(label=_("Postal code"), max_length=24,
                                  required=False)
    country = forms.CharField(label=_("Country"), max_length=100, required=False)

    @classmethod
    def for_organization(cls, organization: Organization, data=None):  # noqa: ANN206
        return cls(data=data, initial={
            field: getattr(organization, field) for field in cls.base_fields
        })

    def clean_name(self) -> str:
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError(_("An organization needs a name."))
        return name


class AddMemberForm(StyledForm):
    """Add an existing account to the organization.

    By email, because that is the identifier a colleague knows. There is
    no invitation by email in this version — nothing is sent outbound —
    so the person must already have an account; if they do not, the form
    says so plainly rather than silently doing nothing.
    """

    email = forms.EmailField(label=_("Their work email"))
    role = forms.ChoiceField(
        label=_("Role"), choices=MemberRole.choices, initial=MemberRole.MEMBER,
    )
    job_title = forms.CharField(label=_("Job title"), max_length=120, required=False)

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()


class MemberRoleForm(StyledForm):
    role = forms.ChoiceField(label=_("Role"), choices=MemberRole.choices)
