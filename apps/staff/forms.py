"""Staff administration forms. Validation only; services do the writing."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledForm
from apps.organizations.models import Organization
from apps.permissions.models import Role
from apps.staff.models import AssignmentRole


class StaffAccountForm(StyledForm):
    """Create a staff account.

    The password is set here by the creator, because there is no outbound
    email to send a setup link through. The holder changes it themselves
    afterwards; the field's help text says so.
    """

    account_type = forms.ChoiceField(choices=[("staff", "Staff"), ("system_owner", "System Owner")],
                                     required=False, initial="staff")

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if actor and not actor.is_super_admin:
            self.fields["account_type"].choices = [("staff", "Staff")]
            self.fields.pop("django_admin_access")
            self.fields.pop("has_all_client_access")

    email = forms.EmailField(label=_("Work email"))
    full_name = forms.CharField(label=_("Full name"), max_length=150)
    job_title = forms.CharField(label=_("Job title"), max_length=120, required=False)
    department = forms.CharField(label=_("Department"), max_length=120, required=False)

    password = forms.CharField(
        label=_("Temporary password"),
        widget=forms.PasswordInput,
        help_text=_(
            "Give it to them directly. They change it after signing in — "
            "the platform sends no email."
        ),
    )

    roles = forms.ModelMultipleChoiceField(
        label=_("Roles"),
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    has_all_client_access = forms.BooleanField(
        label=_("Access to every client"),
        required=False,
        help_text=_(
            "Leave off unless this person's work genuinely spans the "
            "whole book. Everyone else sees only assigned clients."
        ),
    )
    django_admin_access = forms.BooleanField(
        label=_("Django admin access"),
        required=False,
        help_text=_("Separate from the staff dashboard. Rarely needed."),
    )

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()


class StaffProfileForm(StyledForm):
    full_name = forms.CharField(label=_("Full name"), max_length=150, required=False)
    email = forms.EmailField(label=_("Work email"), required=False)
    job_title = forms.CharField(label=_("Job title"), max_length=120, required=False)
    department = forms.CharField(label=_("Department"), max_length=120, required=False)
    notes = forms.CharField(
        label=_("Internal notes"), required=False, widget=forms.Textarea(attrs={"rows": 3})
    )


class RoleAssignmentForm(StyledForm):
    roles = forms.ModelMultipleChoiceField(
        label=_("Roles"),
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )


class ClientAssignmentForm(StyledForm):
    organization = forms.ModelChoiceField(
        label=_("Client"),
        queryset=Organization.objects.all(),
        empty_label=_("Choose a client"),
    )
    role = forms.ChoiceField(
        label=_("Role on this account"),
        choices=AssignmentRole.choices,
        initial=AssignmentRole.SPECIALIST,
    )
    is_primary = forms.BooleanField(label=_("Primary contact"), required=False)


class RoleForm(StyledForm):
    name = forms.CharField(label=_("Role name"), max_length=120)
    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("What this role is for, in a sentence."),
    )


class OverrideForm(StyledForm):
    """A personal exception to the roles.

    Deliberately asks for a reason: an exception nobody can explain later
    is an exception nobody can safely remove.
    """

    permission = forms.ChoiceField(label=_("Permission"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.permissions.catalogue import all_codenames

        self.fields["permission"].choices = [
            (key, key.replace("_", " ").title()) for key in all_codenames()
        ]

    effect = forms.ChoiceField(
        label=_("Effect"),
        choices=[("grant", _("Grant")), ("deny", _("Deny — beats every role"))],
    )
    reason = forms.CharField(label=_("Reason"), max_length=255)
