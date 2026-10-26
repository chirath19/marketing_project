"""Public contact forms, and the staff forms that work the pipeline.

The public form carries three defences a person never notices: a honeypot
field, a signed timestamp that reveals a submission made faster than
anyone could type, and the ordinary validation below. The fourth — a rate
limit — belongs to the view, because it is a property of the request
rather than the data.
"""

from __future__ import annotations

import time

from django import forms
from django.core import signing
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledForm
from apps.leads.models import Lead, LeadSource, LeadStatus

TIMESTAMP_SALT = "leads.form-timestamp"


class PublicFormProtectionMixin(forms.Form):
    """Honeypot plus a signed timestamp.

    The timestamp is signed so it cannot simply be replaced with an older
    value; it carries no personal data, only when the form was rendered.

    A `forms.Form` rather than a plain mixin, and that is load-bearing:
    Django's form metaclass collects declared fields only from bases that
    already have `declared_fields`. As a plain class these two fields were
    silently never added to the form at all — the honeypot existed in the
    source and nowhere else.
    """

    website_url = forms.CharField(
        required=False, label=_("Leave this field empty"),
        widget=forms.TextInput(attrs={
            "tabindex": "-1", "autocomplete": "off", "aria-hidden": "true",
        }),
    )
    rendered_at = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["rendered_at"].initial = signing.dumps(
                time.time(), salt=TIMESTAMP_SALT
            )

    def clean_website_url(self) -> str:
        if self.cleaned_data.get("website_url"):
            # Deliberately vague: naming the trap teaches whoever tripped
            # it how to avoid it next time.
            raise forms.ValidationError(
                _("That submission could not be processed."), code="honeypot"
            )
        return ""

    @property
    def elapsed_seconds(self) -> float | None:
        """How long the form was open, or None if that cannot be told.

        None rather than zero when the token is missing or tampered with:
        "unknown" must not read as "instant", which would flag every
        submission from someone with a stale page.
        """
        raw = self.data.get("rendered_at") if self.is_bound else None
        if not raw:
            return None
        try:
            rendered = signing.loads(raw, salt=TIMESTAMP_SALT, max_age=60 * 60 * 6)
        except signing.BadSignature:
            return None
        return max(0.0, time.time() - float(rendered))


#: What a visitor is trying to achieve. Offered as a choice rather than a
#: free-text box because the answer routes the enquiry, and six words
#: typed in a hurry route nothing. "Something else" keeps the list honest.
OBJECTIVE_CHOICES = [
    ("", _("Select one — optional")),
    ("more_leads", _("Generate more enquiries or leads")),
    ("more_sales", _("Increase online sales")),
    ("visibility", _("Be found in search")),
    ("brand", _("Build brand awareness")),
    ("tracking", _("Understand and measure what is working")),
    ("retention", _("Keep existing customers engaged")),
    ("other", _("Something else")),
]

#: Deliberately wide, unlabelled bands. A visitor who is made to name a
#: figure before anyone has scoped anything usually names nothing and
#: leaves instead.
BUDGET_CHOICES = [
    ("", _("Prefer not to say")),
    ("under_1k", _("Under 1,000 a month")),
    ("1k_3k", _("1,000 – 3,000 a month")),
    ("3k_7k", _("3,000 – 7,000 a month")),
    ("over_7k", _("Over 7,000 a month")),
    ("one_off", _("One-off project")),
    ("unsure", _("Not sure yet")),
]


class ContactForm(PublicFormProtectionMixin, StyledForm):
    """The public enquiry form."""

    name = forms.CharField(
        label=_("Your name"), max_length=150,
        help_text=_("So we know who we are replying to."),
    )
    company = forms.CharField(
        label=_("Company"), max_length=200, required=False,
        help_text=_("Optional."),
    )
    email = forms.EmailField(
        label=_("Email address"), max_length=254,
        help_text=_("Where we reply. We do not add you to any mailing list."),
    )
    phone = forms.CharField(
        label=_("Phone"), max_length=32, required=False,
        help_text=_("Optional, if you would rather talk than type."),
    )
    website = forms.URLField(
        label=_("Website"), max_length=300, required=False,
        help_text=_("Optional, and useful — it saves us both a round of "
                    "questions. Include https://"),
    )
    subject = forms.CharField(label=_("Subject"), max_length=200, required=False,
                              help_text=_("Optional."))
    message = forms.CharField(
        label=_("What are you trying to achieve?"),
        widget=forms.Textarea(attrs={"rows": 5}),
        max_length=4000,
        help_text=_("Your goals, the challenges you are hitting, and which "
                    "services you are considering. The more context, the "
                    "more useful our reply."),
    )

    field_order = ["name", "company", "email", "phone", "website", "subject",
                   "message"]

    def clean_email(self) -> str:
        return self.cleaned_data["email"].strip().lower()

    def clean_message(self) -> str:
        message = self.cleaned_data["message"].strip()
        if len(message) < 10:
            raise forms.ValidationError(
                _("Tell us a little more so we can reply usefully.")
            )
        return message


class QuoteRequestForm(ContactForm):
    """The quote builder's submission form.

    Mostly the same fields, because the same person is writing — the
    difference is that the selection travels with it, so the message no
    longer has to carry the intent and two questions worth asking can be
    asked instead.
    """

    objective = forms.ChoiceField(
        label=_("Main objective"), choices=OBJECTIVE_CHOICES, required=False,
        help_text=_("What success would look like for you."),
    )
    budget_range = forms.ChoiceField(
        label=_("Approximate budget"), choices=BUDGET_CHOICES, required=False,
        help_text=_("Optional. It helps us scope sensibly rather than guess, "
                    "and nothing is fixed by answering."),
    )

    field_order = ["name", "company", "email", "phone", "website",
                   "objective", "budget_range", "message"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["message"].label = _("Anything else we should know?")
        self.fields["message"].required = False
        self.fields["message"].help_text = _(
            "Deadlines, what you have tried already, anything unusual about "
            "your market."
        )
        self.fields["message"].widget.attrs["rows"] = 3
        # The selection says what is wanted, so a subject line adds nothing.
        del self.fields["subject"]

    def objective_label(self) -> str:
        """The wording the visitor saw, not the key we stored it under."""
        chosen = self.cleaned_data.get("objective")
        return dict(OBJECTIVE_CHOICES).get(chosen, "") if chosen else ""

    def budget_label(self) -> str:
        chosen = self.cleaned_data.get("budget_range")
        return dict(BUDGET_CHOICES).get(chosen, "") if chosen else ""

    def clean_message(self) -> str:
        # The selection carries the intent, so a short note is fine here.
        return (self.cleaned_data.get("message") or "").strip()


# ---------------------------------------------------------------------------
# Staff forms
# ---------------------------------------------------------------------------


class LeadNoteForm(StyledForm):
    body = forms.CharField(
        label=_("Internal note"),
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Staff only. The client never sees this."),
    )


class LeadStatusForm(StyledForm):
    status = forms.ChoiceField(label=_("Status"), choices=LeadStatus.choices)
    note = forms.CharField(label=_("Note"), required=False, max_length=250)


class LeadAssignForm(StyledForm):
    assignee = forms.ModelChoiceField(
        label=_("Assign to"), queryset=None, required=False,
        empty_label=_("Nobody"),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        from django.contrib.auth import get_user_model

        from apps.accounts.models import AccountStatus, UserType

        self.fields["assignee"].queryset = (
            get_user_model().objects
            .filter(status=AccountStatus.ACTIVE,
                    user_type__in=[UserType.STAFF, UserType.SUPER_ADMIN])
            .order_by("full_name", "email")
        )


class LeadDetailsForm(StyledForm):
    """The parts of a lead staff may correct.

    The submission itself is never edited — it is the record of what was
    sent. This is the agency's working copy.
    """

    name = forms.CharField(label=_("Name"), max_length=150)
    company = forms.CharField(label=_("Company"), max_length=200, required=False)
    phone = forms.CharField(label=_("Phone"), max_length=32, required=False)
    website = forms.URLField(label=_("Website"), max_length=300, required=False)
    source = forms.ChoiceField(label=_("Source"), choices=LeadSource.choices)
    estimated_value = forms.DecimalField(
        label=_("Estimated monthly value"), required=False,
        max_digits=12, decimal_places=2, min_value=0,
    )

    @classmethod
    def for_lead(cls, lead: Lead, data=None):  # noqa: ANN206
        return cls(data=data, initial={
            field: getattr(lead, field) for field in cls.base_fields
        })


# ---------------------------------------------------------------------------
# Quote request forms
# ---------------------------------------------------------------------------


class QuoteStatusForm(StyledForm):
    status = forms.ChoiceField(label=_("Move to"), choices=[])
    note = forms.CharField(
        label=_("Note"), required=False, max_length=250,
        help_text=_("Optional. Recorded on the timeline beside the change."),
    )

    def __init__(self, *args, quote=None, **kwargs) -> None:  # noqa: ANN001
        super().__init__(*args, **kwargs)

        from apps.leads.models import QuoteStatus
        from apps.leads.quote_services import ALLOWED_TRANSITIONS

        # Only the moves this quote can actually make. Offering the rest
        # and rejecting them afterwards teaches people to distrust the
        # form, and the service layer would refuse them anyway.
        allowed = ALLOWED_TRANSITIONS.get(getattr(quote, "status", ""), frozenset())
        labels = dict(QuoteStatus.choices)
        self.fields["status"].choices = [
            (value, labels[value]) for value in QuoteStatus.values if value in allowed
        ]


class QuoteAssignForm(StyledForm):
    assignee = forms.ModelChoiceField(
        label=_("Owner"), queryset=None, required=False,
        empty_label=_("Nobody"),
        help_text=_("Whoever is pricing this. They are notified when the "
                    "client replies."),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        from django.contrib.auth import get_user_model

        from apps.accounts.models import AccountStatus, UserType

        self.fields["assignee"].queryset = (
            get_user_model().objects
            .filter(status=AccountStatus.ACTIVE,
                    user_type__in=[UserType.STAFF, UserType.SUPER_ADMIN])
            .order_by("full_name", "email")
        )


class QuoteScopeForm(StyledForm):
    """The scope summary the client eventually reads."""

    summary = forms.CharField(
        label=_("Scope summary"), required=False,
        widget=forms.Textarea(attrs={"rows": 5}), max_length=4000,
        help_text=_("What we are proposing, in plain language. The client "
                    "sees this once the proposal is marked ready — not "
                    "before, so a half-written note cannot cause the "
                    "conversation it was meant to prevent."),
    )


class QuoteNoteForm(StyledForm):
    body = forms.CharField(
        label=_("Note"), widget=forms.Textarea(attrs={"rows": 3}),
        max_length=4000,
    )
    share_with_client = forms.BooleanField(
        label=_("Show this to the client"), required=False,
        help_text=_("Off by default. An internal note is never shown in "
                    "their workspace."),
    )


class QuoteOrganizationForm(StyledForm):
    organization = forms.ModelChoiceField(
        label=_("Client organization"), queryset=None, required=False,
        empty_label=_("Not attached to a client"),
        help_text=_("Attaching it makes the quote visible in that client's "
                    "own workspace."),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        from apps.organizations.models import Organization

        self.fields["organization"].queryset = Organization.objects.order_by("name")


class ClientQuoteReplyForm(StyledForm):
    """What a client can write back on their own quote."""

    body = forms.CharField(
        label=_("Your message"), widget=forms.Textarea(attrs={"rows": 4}),
        max_length=5000,
        help_text=_("Questions, changes of scope, anything we should know. "
                    "It stays in your workspace — nothing is emailed."),
    )

    def clean_body(self) -> str:
        body = self.cleaned_data["body"].strip()
        if not body:
            raise forms.ValidationError(_("Tell us a little more."))
        return body


class ClientQuoteCreateForm(StyledForm):
    services = forms.ModelMultipleChoiceField(queryset=None, required=False,
        widget=forms.CheckboxSelectMultiple, label='Services you are interested in')
    message = forms.CharField(required=False, max_length=5000, label='Your request or custom scope',
        widget=forms.Textarea(attrs={'rows': 6}),
        help_text='Describe what you need, even if it is not listed in our catalogue.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.catalog.selectors import live_services
        self.fields['services'].queryset = live_services().filter(can_request_quote=True)
        # CheckboxSelectMultiple applies widget attributes to its containing div.
        # A single-checkbox class would constrain the entire list to 16px.
        self.fields['services'].widget.attrs.pop('class', None)

    def clean(self):
        data = super().clean()
        if not data.get('services') and not data.get('message', '').strip():
            raise forms.ValidationError('Choose a service or describe your custom request.')
        return data


class QuoteLineForm(StyledForm):
    name = forms.CharField(max_length=250, label='Service or custom deliverable')
    quoted_amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    currency = forms.RegexField(r'^[A-Za-z]{3}$', initial='USD', max_length=3)
    billing_type = forms.ChoiceField(choices=[('one_time', 'One-time'), ('monthly', 'Monthly')])
    note = forms.CharField(max_length=250, required=False)
