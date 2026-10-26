"""Account forms.

The sign-in form carries the one subtle piece of this module. The
authentication backend stays strict — it refuses anything that is not
ACTIVE, so no code path anywhere can authenticate a suspended account. A
strict backend alone would leave a pending client staring at "please
enter a correct email and password", which with no outbound email leaves
them no way forward. So on a failed sign-in the form re-checks the
password itself and, only when it is correct, explains the account's
status. The gate and the explanation stay separate.
"""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts import selectors
from apps.accounts.models import AccountStatus
from apps.core.forms import StyledForm, StyledFormMixin, StyledModelForm

User = get_user_model()


STATUS_SIGN_IN_MESSAGES = {
    AccountStatus.PENDING: _(
        "Your account is waiting for approval. Our team reviews new "
        "accounts on working days and you will be able to sign in as soon "
        "as yours is approved."
    ),
    AccountStatus.SUSPENDED: _(
        "This account is suspended. Please contact your account manager."
    ),
    AccountStatus.DISABLED: _(
        "This account has been closed. Please contact your account manager "
        "if you think that is a mistake."
    ),
}


class LoginForm(StyledFormMixin, AuthenticationForm):
    """Email-and-password sign in."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Email address")
        self.fields["username"].widget.attrs.update(
            {"autocomplete": "email", "autofocus": True,
             "placeholder": "you@company.com"}
        )
        self.fields["password"].widget.attrs.update(
            {"autocomplete": "current-password"}
        )

    def clean(self):
        try:
            return super().clean()
        except ValidationError as exc:
            if getattr(exc, "code", None) == "invalid_login":
                self._explain_status_if_password_is_correct()
            raise

    def _explain_status_if_password_is_correct(self) -> None:
        """Replace the generic failure with the real reason — carefully.

        Only ever reached when the submitted password is correct, so this
        tells the account holder something they are entitled to know and
        tells an attacker who guessed the password nothing they could not
        already infer. A wrong password still gets the generic message,
        so the form is not an account-existence oracle.
        """
        user = selectors.get_by_email(self.cleaned_data.get("username", ""))
        if user is None or not user.check_password(self.cleaned_data.get("password", "")):
            return

        message = STATUS_SIGN_IN_MESSAGES.get(user.status)
        if message:
            raise ValidationError(message, code="inactive_account")


class RegistrationForm(StyledModelForm):
    """Client self-registration.

    Abuse protection is layered: a honeypot the form rejects outright,
    per-address rate limiting applied by the view, Django's password
    validators, and the database's unique constraint as the final word on
    duplicates.
    """

    password1 = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text=_("At least 10 characters, and not something easily guessed."),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    # Not a real field. Hidden from people, left empty by them, and filled
    # in by the naive bots that submit every input they find.
    website_url = forms.CharField(
        required=False,
        label=_("Leave this field empty"),
        widget=forms.TextInput(attrs={
            "tabindex": "-1", "autocomplete": "off", "aria-hidden": "true",
        }),
    )

    # Not a field on User: it names the Organization that registration
    # creates, with the registrant as its owner.
    company_name = forms.CharField(
        label=_("Company"), max_length=200,
        help_text=_("We set up your company's workspace under this name."),
    )

    class Meta:
        model = User
        fields = ["full_name", "email", "phone", "job_title"]
        labels = {
            "full_name": _("Your name"),
            "email": _("Work email"),
            "phone": _("Phone"),
            "job_title": _("Job title"),
        }

    field_order = ["full_name", "email", "company_name", "job_title", "phone",
                   "password1", "password2"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["full_name"].required = True
        self.fields["phone"].required = False
        self.fields["job_title"].required = False
        self.fields["email"].widget.attrs.update(
            {"autocomplete": "email", "placeholder": "you@company.com"}
        )
        self.fields["full_name"].widget.attrs.update({"autocomplete": "name"})
        self.fields["company_name"].widget.attrs.update({"autocomplete": "organization"})

    def clean_website_url(self) -> str:
        if self.cleaned_data.get("website_url"):
            # Deliberately vague. Naming the trap teaches whoever tripped
            # it how to avoid it next time.
            raise ValidationError(_("That submission could not be processed."),
                                  code="honeypot")
        return ""

    def clean_email(self) -> str:
        """Normalise, then reject an address that is already registered.

        This does reveal that an address has an account. The alternative —
        accepting silently and emailing the real owner — is not available
        here, and leaving a visitor unable to tell a typo from a duplicate
        is worse. Enumeration is bounded by the registration rate limit
        instead.
        """
        email = User.objects.normalize_email(
            self.cleaned_data.get("email", "")
        ).lower().strip()

        if not email:
            raise ValidationError(_("Enter your work email address."))

        if selectors.email_is_taken(email):
            raise ValidationError(
                _("An account already exists for this email address. "
                  "Try signing in instead."),
                code="duplicate_email",
            )

        return email

    def clean_password2(self) -> str:
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError(_("The two passwords do not match."),
                                  code="password_mismatch")
        return password2

    def _post_clean(self) -> None:
        super()._post_clean()

        password = self.cleaned_data.get("password1")
        if not password:
            return

        # Validated against the user's own details, so an address or name
        # cannot be reused as the password.
        try:
            validate_password(password, self.instance)
        except ValidationError as exc:
            self.add_error("password1", exc)

    def save(self, commit: bool = True):
        """Not used. Registration goes through the service layer.

        A ModelForm that can quietly create a user would bypass the
        status decision, the event and the logging in
        `services.register_client`.
        """
        raise NotImplementedError(
            "Use apps.accounts.services.register_client() instead of "
            "RegistrationForm.save()."
        )


class ProfileForm(StyledForm):
    """The details a user may change about themselves.

    A plain form, not a ModelForm, on purpose. A ModelForm writes the
    submitted values onto its `instance` during validation — so by the
    time the service compared old against new, the "old" value was
    already the new one and nothing was ever saved. Keeping the form free
    of the model leaves the write entirely to the service layer, which is
    where it belongs anyway.

    Email is absent on purpose — see `services.update_profile`.
    """

    full_name = forms.CharField(label=_("Your name"), max_length=150)
    phone = forms.CharField(label=_("Phone"), max_length=32, required=False)
    job_title = forms.CharField(label=_("Job title"), max_length=120, required=False)

    @classmethod
    def for_user(cls, user, data=None):  # noqa: ANN001, ANN206
        return cls(
            data=data,
            initial={
                "full_name": user.full_name,
                "phone": user.phone,
                "job_title": user.job_title,
            },
        )


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    """Django's password change, with the design system's styling.

    The current password is required, which is what stops a borrowed
    session from locking the real owner out of their account.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update(
            {"autocomplete": "current-password", "autofocus": True}
        )
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs.update({"autocomplete": "new-password"})
