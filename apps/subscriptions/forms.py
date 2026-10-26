"""Forms for attaching and working client services.

The staff forms here are the manual path the brief asks for: an
administrator assigning a service to a client directly, without a quote
in front of it. The quote path produces the same rows through the same
service functions, so the two cannot drift apart.
"""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledForm
from apps.subscriptions.models import ClientSubscription, SubscriptionStatus


class SubscriptionForm(StyledForm):
    """Attach a service to a client, or correct one already attached."""

    service = forms.ModelChoiceField(
        label=_("Service"), queryset=None,
        help_text=_("From the catalogue. Price and billing are copied from "
                    "it and can then be adjusted for this client."),
    )
    package = forms.ModelChoiceField(
        label=_("Package"), queryset=None, required=False,
        empty_label=_("No package"),
        help_text=_("Only where the service has tiers."),
    )
    name = forms.CharField(
        label=_("As sold"), max_length=250, required=False,
        help_text=_("Defaults to the service name. Kept as it was sold, so "
                    "renaming the catalogue cannot rewrite history."),
    )

    price = forms.DecimalField(
        label=_("Price"), max_digits=12, decimal_places=2, required=False,
        min_value=0,
        help_text=_("Leave blank to quote this service on scope."),
    )
    currency = forms.CharField(label=_("Currency"), max_length=3, required=False,
                               help_text=_("Defaults to the catalogue's."))
    billing_type = forms.ChoiceField(
        label=_("Billing"), required=False,
        choices=[("", _("From the catalogue")), ("monthly", _("Per month")),
                 ("one_time", _("One time")), ("custom", _("Custom"))],
    )

    custom_scope = forms.CharField(
        label=_("Agreed scope"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Where this client's arrangement differs from the "
                    "standard catalogue scope."),
    )

    starts_on = forms.DateField(
        label=_("Starts"), required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Set automatically when you activate it, if left blank."),
    )
    ends_on = forms.DateField(
        label=_("Ends"), required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text=_("Leave blank for an ongoing service with no agreed end."),
    )

    client_notes = forms.CharField(
        label=_("Notes for the client"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Shown in their workspace beside this service. Write it "
                    "as if they are reading it, because they are."),
    )
    internal_notes = forms.CharField(
        label=_("Internal notes"), required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Staff only. The client never sees this."),
    )

    field_order = ["service", "package", "name", "price", "currency",
                   "billing_type", "starts_on", "ends_on", "custom_scope",
                   "client_notes", "internal_notes"]

    def __init__(self, *args, organization=None, instance=None, **kwargs) -> None:  # noqa: ANN001
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.instance = instance

        from apps.catalog.models import Service, ServicePackage

        self.fields["service"].queryset = (
            Service.objects.filter(is_active=True)
            .select_related("category").order_by("category__order", "order", "name")
        )
        self.fields["package"].queryset = (
            ServicePackage.objects.select_related("service").order_by("service__name",
                                                                     "order")
        )

    def clean(self) -> dict:
        cleaned = super().clean()
        service = cleaned.get("service")
        package = cleaned.get("package")
        starts, ends = cleaned.get("starts_on"), cleaned.get("ends_on")

        if package and service and package.service_id != service.pk:
            self.add_error("package",
                           _("That package belongs to a different service."))

        if starts and ends and ends < starts:
            self.add_error("ends_on", _("A service cannot end before it starts."))

        # Caught here as well as by the database constraint, so the person
        # gets a sentence instead of an integrity error.
        if service and self.organization is not None:
            clash = ClientSubscription.objects.filter(
                organization=self.organization, service=service,
                status__in=["pending", "active", "paused"],
            )
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                self.add_error("service", _(
                    "This client already has that service open. Edit the "
                    "existing one, or close it first."
                ))

        return cleaned

    @classmethod
    def for_subscription(cls, subscription, data=None):  # noqa: ANN001, ANN206
        return cls(
            data=data, organization=subscription.organization,
            instance=subscription,
            initial={
                "service": subscription.service_id,
                "package": subscription.package_id,
                "name": subscription.name,
                "price": subscription.price,
                "currency": subscription.currency,
                "billing_type": subscription.billing_type,
                "custom_scope": subscription.custom_scope,
                "starts_on": subscription.starts_on,
                "ends_on": subscription.ends_on,
                "client_notes": subscription.client_notes,
                "internal_notes": subscription.internal_notes,
            },
        )


class SubscriptionStatusForm(StyledForm):
    status = forms.ChoiceField(label=_("Move to"), choices=[])
    note = forms.CharField(
        label=_("Note"), required=False, max_length=250,
        help_text=_("Optional. Recorded in the history beside the change."),
    )

    def __init__(self, *args, subscription=None, **kwargs) -> None:  # noqa: ANN001
        super().__init__(*args, **kwargs)

        from apps.subscriptions.services import ALLOWED_TRANSITIONS

        # Only the moves this service can actually make. Offering the
        # rest and refusing them afterwards teaches people to distrust
        # the form, and the service layer would refuse them anyway.
        allowed = ALLOWED_TRANSITIONS.get(getattr(subscription, "status", ""),
                                          frozenset())
        labels = dict(SubscriptionStatus.choices)
        self.fields["status"].choices = [
            (value, labels[value]) for value in SubscriptionStatus.values
            if value in allowed
        ]


class SubscriptionNoteForm(StyledForm):
    body = forms.CharField(
        label=_("Note"), widget=forms.Textarea(attrs={"rows": 3}), max_length=4000,
    )
    share_with_client = forms.BooleanField(
        label=_("Show this to the client"), required=False,
        help_text=_("Off by default. An internal note is never shown in "
                    "their workspace."),
    )
