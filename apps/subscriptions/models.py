"""What each client is actually paying for.

This is the relationship the rest of the platform hangs off. A campaign
belongs to a subscription, a report reports on one, and what a client
sees in their workspace is decided by which of these are active — so
there is **one** workspace, not a dashboard built per client.

`ClientSubscription` inherits `OrganizationOwnedModel`, which is the
single implementation of the tenant isolation rule. That is deliberate
and it is the whole reason the base exists: this domain does not get to
invent its own idea of who may see what.

Models hold structure and invariants only. The workflow lives in
`services.py`.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.modules import get_module
from apps.organizations.models import OrganizationOwnedModel, OrganizationOwnedQuerySet


class SubscriptionStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    ACTIVE = "active", _("Active")
    PAUSED = "paused", _("Paused")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    EXPIRED = "expired", _("Expired")


#: Statuses that mean the agency is working. Only these unlock a module
#: in the client's workspace — a paused service should not keep showing
#: live data, and a cancelled one certainly should not.
DELIVERING_STATUSES = frozenset({SubscriptionStatus.ACTIVE})

#: Statuses that are still part of the current relationship, whether or
#: not work is happening right now.
OPEN_STATUSES = frozenset(
    {
        SubscriptionStatus.PENDING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAUSED,
    }
)

#: Finished, one way or another. Kept, never deleted.
CLOSED_STATUSES = frozenset(
    {
        SubscriptionStatus.COMPLETED,
        SubscriptionStatus.CANCELLED,
        SubscriptionStatus.EXPIRED,
    }
)


class ClientSubscriptionQuerySet(OrganizationOwnedQuerySet):
    """Scoping, plus the three questions actually asked of this table.

    Inherits `visible_to` from the tenancy base rather than redefining
    it. There is one isolation rule and this is not the place to have
    opinions about it.
    """

    def for_listing(self) -> models.QuerySet:
        return self.select_related(
            "organization",
            "service",
            "service__category",
            "package",
            "created_by",
        )

    def delivering(self) -> models.QuerySet:
        return self.filter(status__in=DELIVERING_STATUSES)

    def open(self) -> models.QuerySet:
        return self.filter(status__in=OPEN_STATUSES)

    def due_to_expire(self, *, on=None) -> models.QuerySet:  # noqa: ANN001
        """Active or paused services whose end date has passed.

        Expiry is a status rather than a calculation so that the history
        records when it happened and who was told. This finds the ones a
        person — or a scheduled command — still has to act on.
        """
        return self.filter(
            status__in={SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED},
            ends_on__lt=on or timezone.localdate(),
        )


class ClientSubscription(OrganizationOwnedModel, TimeStampedModel):
    """One service, sold to one client, for a period."""

    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name=_("service"),
        help_text=_(
            "Protected on purpose: retiring a service that clients "
            "are still paying for should fail loudly."
        ),
    )
    package = models.ForeignKey(
        "catalog.ServicePackage",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subscriptions",
        verbose_name=_("package"),
    )

    #: What it was called when it was sold. Copied, like a quote line:
    #: renaming a catalogue entry must not rewrite what a client agreed
    #: to two years ago.
    name = models.CharField(
        _("as sold"),
        max_length=250,
        help_text=_(
            "Defaults to the service name. Kept as it was sold, so "
            "renaming the catalogue cannot rewrite history."
        ),
    )

    # --- what it costs ----------------------------------------------------

    price = models.DecimalField(
        _("price"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Leave blank for a service quoted on scope."),
    )
    currency = models.CharField(_("currency"), max_length=3, default="USD")
    billing_type = models.CharField(
        _("billing"),
        max_length=20,
        blank=True,
        help_text=_("one_time, monthly or custom."),
    )

    custom_scope = models.TextField(
        _("agreed scope"),
        blank=True,
        help_text=_(
            "What this particular client is getting, where it "
            "differs from the standard catalogue scope."
        ),
    )

    # --- the period -------------------------------------------------------

    starts_on = models.DateField(
        _("starts"),
        null=True,
        blank=True,
        help_text=_("Set when the work actually begins. A pending service may not have one yet."),
    )
    ends_on = models.DateField(
        _("ends"),
        null=True,
        blank=True,
        help_text=_("Leave blank for an ongoing service with no agreed end."),
    )

    # --- working it -------------------------------------------------------

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING,
        db_index=True,
    )

    internal_notes = models.TextField(
        _("internal notes"),
        blank=True,
        help_text=_("Staff only. The client never sees this."),
    )
    client_notes = models.TextField(
        _("notes for the client"),
        blank=True,
        help_text=_(
            "Shown in the client's workspace beside this service. "
            "Write it as if they are reading it, because they are."
        ),
    )

    quote = models.ForeignKey(
        "leads.QuoteRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
        verbose_name=_("from quote"),
        help_text=_("The accepted quote this came from, when there was one."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_subscriptions",
        verbose_name=_("set up by"),
    )

    activated_at = models.DateTimeField(_("activated"), null=True, blank=True)
    ended_at = models.DateTimeField(_("ended"), null=True, blank=True)

    objects = ClientSubscriptionQuerySet.as_manager()

    class Meta:
        verbose_name = _("client service")
        verbose_name_plural = _("client services")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["organization", "status"], name="sub_org_status_idx"),
            models.Index(fields=["status", "-created_at"], name="sub_status_created_idx"),
            models.Index(fields=["service", "status"], name="sub_service_idx"),
            models.Index(fields=["ends_on"], name="sub_ends_idx"),
        ]
        constraints = [
            # A client can hold the same service more than once over the
            # years, but not twice at the same time — that is a
            # double-charge waiting to happen, and it makes "is this
            # client getting SEO?" ambiguous.
            models.UniqueConstraint(
                fields=["organization", "service"],
                condition=models.Q(status__in=["pending", "active", "paused"]),
                name="one_open_subscription_per_service",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization} — {self.name}"

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("staff:subscription_detail", kwargs={"pk": self.pk})

    def clean(self) -> None:
        super().clean()

        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError(
                {
                    "ends_on": _("A service cannot end before it starts."),
                }
            )

        if self.package_id and self.service_id and self.package.service_id != self.service_id:
            raise ValidationError(
                {
                    "package": _("That package belongs to a different service."),
                }
            )

    # --- derived -----------------------------------------------------------

    @property
    def is_delivering(self) -> bool:
        return self.status in DELIVERING_STATUSES

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def workspace_module(self):  # noqa: ANN201
        """The module this service unlocks, if any.

        Read from the service's category rather than stored here, so that
        changing which area a category belongs to takes effect for every
        client at once instead of leaving old rows pointing at the old
        answer.
        """
        category = getattr(self.service, "category", None)
        return get_module(getattr(category, "workspace_module", ""))

    @property
    def is_past_end(self) -> bool:
        """Still open, but the agreed end date has gone by."""
        return bool(self.ends_on and self.is_open and self.ends_on < timezone.localdate())

    @property
    def price_display(self) -> str:
        if self.price is None:
            return _("Custom quote")
        return f"{self.currency} {self.price:,.2f}"

    @property
    def billing_display(self) -> str:
        return {
            "monthly": _("per month"),
            "one_time": _("one time"),
        }.get(self.billing_type, "")


class SubscriptionEventKind(models.TextChoices):
    CREATED = "created", _("Service added")
    STATUS = "status", _("Status changed")
    SCOPE = "scope", _("Scope or price changed")
    NOTE = "note", _("Note")


class SubscriptionEvent(TimeStampedModel):
    """One entry in a service's history.

    Append-only in practice: written by the service layer and never
    edited, so "when did this client's SEO actually start?" has an answer
    somebody can trust.

    Reached through its subscription for isolation, which is how the
    tenancy guard traces it to an owner without denormalising the
    organization onto every row.
    """

    subscription = models.ForeignKey(
        ClientSubscription,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=_("service"),
    )
    kind = models.CharField(
        _("kind"),
        max_length=20,
        choices=SubscriptionEventKind.choices,
        default=SubscriptionEventKind.NOTE,
    )
    body = models.TextField(_("detail"), blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscription_events",
        verbose_name=_("by"),
    )
    is_internal = models.BooleanField(
        _("internal"),
        default=True,
        help_text=_("Internal entries are never shown to the client."),
    )

    class Meta:
        verbose_name = _("service history entry")
        verbose_name_plural = _("service history")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["subscription", "-created_at"], name="subevent_sub_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.subscription_id}: {self.get_kind_display()}"


class BillingSequence(models.Model):
    """Serialized, yearly numbering for newly issued billing documents."""

    key = models.CharField(max_length=20, unique=True)
    value = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.key


class PaymentReceipt(OrganizationOwnedModel, TimeStampedModel):
    """A staff-recorded payment acknowledgement; no payment is collected here."""

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payment_receipts"
    )
    invoice = models.ForeignKey(
        "subscriptions.Invoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="receipts",
    )
    subscription = models.ForeignKey(
        ClientSubscription, on_delete=models.PROTECT, null=True, blank=True, related_name="receipts"
    )
    reference = models.CharField(max_length=100, unique=True)
    submission_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    paid_on = models.DateField()
    payment_method = models.CharField(max_length=100)
    notes = models.TextField(max_length=3000, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-paid_on", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="receipt_positive_amount")
        ]

    def __str__(self):
        return self.reference

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Enter a positive payment amount."})
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValidationError({"currency": "Use a three-letter currency code."})
        if self.paid_on and self.paid_on > timezone.localdate():
            raise ValidationError({"paid_on": "A receipt cannot acknowledge a future payment."})


class Invoice(OrganizationOwnedModel, TimeStampedModel):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices"
    )
    subscription = models.ForeignKey(
        ClientSubscription, on_delete=models.PROTECT, null=True, blank=True, related_name="invoices"
    )
    quote = models.ForeignKey(
        "leads.QuoteRequest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
    )
    reference = models.CharField(max_length=100, unique=True)
    submission_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    description = models.TextField(max_length=5000)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    issued_on = models.DateField(default=timezone.localdate)
    due_on = models.DateField()
    published_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-issued_on", "-pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="invoice_positive_amount")
        ]

    def __str__(self):
        return self.reference

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "Enter a positive invoice amount."
        if len(self.currency) != 3 or not self.currency.isalpha():
            errors["currency"] = "Use a three-letter currency code."
        if self.due_on and self.issued_on and self.due_on < self.issued_on:
            errors["due_on"] = "The due date cannot precede the issue date."
        for field in ["subscription", "quote"]:
            obj = getattr(self, field)
            if obj and obj.organization_id != self.organization_id:
                errors[field] = "Choose a record belonging to this client organization."
        if errors:
            raise ValidationError(errors)

    @property
    def paid_amount(self):
        from decimal import Decimal

        return sum(
            (receipt.amount for receipt in self.receipts.all() if not receipt.voided_at),
            Decimal("0"),
        )

    @property
    def balance(self):
        return self.amount - self.paid_amount

    @property
    def payment_status(self):
        if self.voided_at:
            return "Voided"
        if not self.published_at:
            return "Draft"
        if self.balance <= 0:
            return "Paid"
        if self.due_on < timezone.localdate():
            return "Overdue"
        return "Partially paid" if self.paid_amount else "Awaiting payment"


class ServiceChangeRequest(OrganizationOwnedModel, TimeStampedModel):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_requests"
    )
    subscription = models.ForeignKey(
        ClientSubscription, on_delete=models.PROTECT, related_name="change_requests"
    )
    kind = models.CharField(
        max_length=20,
        choices=[
            ("renewal", "Renewal"),
            ("extension", "Duration extension"),
            ("extra", "Extra deliverables"),
            ("additional", "Additional service"),
        ],
    )
    requirements = models.TextField(max_length=5000)
    requested_end = models.DateField(null=True, blank=True)
    additional_service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="change_requests",
    )
    quote = models.OneToOneField(
        "leads.QuoteRequest", on_delete=models.PROTECT, related_name="service_change_request"
    )
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-pk"]

    @property
    def status_label(self):
        return "Applied to service" if self.applied_at else self.quote.get_status_display()
