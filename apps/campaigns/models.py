"""Persistence for the Campaigns domain.

One table for every service. SEO, paid advertising, social and email
campaigns differ in what you measure them by, not in what they *are* —
all of them have a client, a budget, a period, an owner and a status, and
all of them belong in one list. `service_type` discriminates; a detail
record attached through `apps.campaigns.registry` carries whatever a
particular type needs on top.

`Campaign` inherits `OrganizationOwnedModel`, the single implementation
of the tenant isolation rule. This domain does not get its own opinion
about who may see what.

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
from apps.organizations.models import OrganizationOwnedModel, OrganizationOwnedQuerySet


class CampaignStatus(models.TextChoices):
    PLANNED = "planned", _("Planned")
    LIVE = "live", _("Live")
    PAUSED = "paused", _("Paused")
    DONE = "done", _("Done")
    CANCELLED = "cancelled", _("Cancelled")


#: Running right now. The only status that counts as work in progress.
RUNNING_STATUSES = frozenset({CampaignStatus.LIVE})

#: Still part of the current engagement, whether or not it is running.
OPEN_STATUSES = frozenset({
    CampaignStatus.PLANNED, CampaignStatus.LIVE, CampaignStatus.PAUSED,
})

#: Finished, one way or the other. Kept, never deleted.
CLOSED_STATUSES = frozenset({CampaignStatus.DONE, CampaignStatus.CANCELLED})


class CampaignQuerySet(OrganizationOwnedQuerySet):
    """Scoping, plus the questions actually asked of this table.

    Inherits `visible_to` from the tenancy base rather than redefining
    it. There is one isolation rule and this is not the place to have
    opinions about it.
    """

    def for_listing(self) -> models.QuerySet:
        return self.select_related(
            "organization", "owner", "subscription", "subscription__service",
        ).prefetch_related("assignees")

    def running(self) -> models.QuerySet:
        return self.filter(status__in=RUNNING_STATUSES)

    def open(self) -> models.QuerySet:
        return self.filter(status__in=OPEN_STATUSES)

    def of_type(self, key: str) -> models.QuerySet:
        """Campaigns for one service area.

        The hook every service module uses. A future SEO dashboard asks
        for `of_type("seo")` rather than querying a table of its own.
        """
        return self.filter(service_type=key)

    def overdue(self, *, on=None) -> models.QuerySet:
        """Open campaigns whose end date has gone by."""
        return self.filter(
            status__in=[CampaignStatus.PLANNED, CampaignStatus.LIVE,
                        CampaignStatus.PAUSED],
            ends_on__lt=on or timezone.localdate(),
        )


class Campaign(OrganizationOwnedModel, TimeStampedModel):
    """One piece of work, run for one client, over a period."""

    #: The commercial record this is delivered under. Nullable, because
    #: work occasionally starts before the paperwork catches up and a
    #: campaign nobody can record is worse than one with a gap in it.
    subscription = models.ForeignKey(
        "subscriptions.ClientSubscription", on_delete=models.PROTECT,
        null=True, blank=True, related_name="campaigns",
        verbose_name=_("client service"),
        help_text=_("The service this is delivered under. Leave blank only "
                    "where there genuinely is not one yet."),
    )

    service_type = models.CharField(
        _("service area"), max_length=30, db_index=True,
        help_text=_("Which part of the client's workspace this belongs in. "
                    "Set from the service when there is one."),
    )

    name = models.CharField(_("name"), max_length=200)
    description = models.TextField(
        _("description"), blank=True,
        help_text=_("What this campaign is and why it is running. Staff "
                    "only."),
    )
    objective = models.CharField(
        _("objective"), max_length=250, blank=True,
        help_text=_("What success looks like. The label shown beside it "
                    "depends on the service area."),
    )

    status = models.CharField(_("status"), max_length=20,
                              choices=CampaignStatus.choices,
                              default=CampaignStatus.PLANNED, db_index=True)

    budget = models.DecimalField(
        _("budget"), max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=_("Media or production budget for the period. Not the "
                    "fee — that lives on the service."),
    )
    currency = models.CharField(_("currency"), max_length=3, default="USD")

    starts_on = models.DateField(_("starts"), null=True, blank=True)
    ends_on = models.DateField(
        _("ends"), null=True, blank=True,
        help_text=_("Leave blank for ongoing work with no agreed end."),
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="owned_campaigns", verbose_name=_("owner"),
        help_text=_("The one person accountable for it."),
    )
    assignees = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="campaigns",
        verbose_name=_("working on it"),
        help_text=_("Everyone else doing the work. The owner is "
                    "accountable; these people are involved."),
    )

    client_summary = models.TextField(
        _("summary for the client"), blank=True,
        help_text=_("Shown in their workspace. Write it as if they are "
                    "reading it, because they are."),
    )
    internal_notes = models.TextField(
        _("internal notes"), blank=True,
        help_text=_("Staff only. The client never sees this."),
    )

    started_at = models.DateTimeField(_("went live"), null=True, blank=True)
    ended_at = models.DateTimeField(_("ended"), null=True, blank=True)

    objects = CampaignQuerySet.as_manager()

    class Meta:
        verbose_name = _("campaign")
        verbose_name_plural = _("campaigns")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["organization", "status"],
                         name="campaign_org_status_idx"),
            models.Index(fields=["service_type", "status"],
                         name="campaign_type_status_idx"),
            models.Index(fields=["status", "-created_at"],
                         name="campaign_status_created_idx"),
            models.Index(fields=["ends_on"], name="campaign_ends_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("staff:campaign_detail", kwargs={"pk": self.pk})

    def clean(self) -> None:
        super().clean()

        from apps.campaigns.registry import get_type

        if get_type(self.service_type) is None:
            raise ValidationError({
                "service_type": _("That is not a service area campaigns can "
                                  "belong to."),
            })

        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError({
                "ends_on": _("A campaign cannot end before it starts."),
            })

        # A campaign delivered under a service must belong to the same
        # client as that service. Without this, attaching the wrong
        # subscription would quietly put one client's work on another
        # client's invoice.
        if self.subscription_id and self.organization_id and \
                self.subscription.organization_id != self.organization_id:
            raise ValidationError({
                "subscription": _("That service belongs to a different "
                                  "client."),
            })

    # --- derived -----------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self.status in RUNNING_STATUSES

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def campaign_type(self):  # noqa: ANN201
        from apps.campaigns.registry import get_type

        return get_type(self.service_type)

    @property
    def type_label(self) -> str:
        campaign_type = self.campaign_type
        return campaign_type.label if campaign_type else self.service_type

    @property
    def objective_label(self) -> str:
        """What "objective" is called for this kind of campaign."""
        campaign_type = self.campaign_type
        return campaign_type.goal_label if campaign_type else _("Objective")

    @property
    def detail(self):  # noqa: ANN201
        """The type-specific record attached to this campaign, if any.

        The other half of the extension point: a service module adds its
        fields here instead of adding a parallel campaign model.
        """
        from apps.campaigns.registry import detail_model_for

        model = detail_model_for(self.service_type)
        if model is None:
            return None
        return model.objects.filter(campaign=self).first()

    @property
    def is_overdue(self) -> bool:
        return bool(self.ends_on and self.is_open
                    and self.ends_on < timezone.localdate())

    @property
    def budget_display(self) -> str:
        if self.budget is None:
            return ""
        return f"{self.currency} {self.budget:,.2f}"


class CampaignDetail(models.Model):
    """Base for a service module's extra campaign fields.

    This is the interface the brief asks for. A module that needs more
    than the core carries subclasses this, adds its own fields, and
    registers the path in `apps.campaigns.registry` — it does **not**
    grow a campaign model of its own, because then the combined list,
    the status machine, the permissions and the isolation rule would all
    have to be written again and kept in step.

        class SeoCampaignDetail(CampaignDetail):
            target_keywords = models.TextField(blank=True)
    """

    campaign = models.OneToOneField(
        Campaign, on_delete=models.CASCADE, related_name="%(app_label)s_detail",
        verbose_name=_("campaign"), primary_key=True,
    )

    class Meta:
        abstract = True


class CampaignEventKind(models.TextChoices):
    CREATED = "created", _("Campaign created")
    STATUS = "status", _("Status changed")
    ASSIGNMENT = "assignment", _("People changed")
    UPDATED = "updated", _("Details changed")
    NOTE = "note", _("Note")


class CampaignEvent(TimeStampedModel):
    """One entry in a campaign's history.

    Append-only in practice: written by the service layer, never edited,
    so "when did this actually go live?" has an answer somebody can
    trust.

    Reached through its campaign for isolation, which is how the tenancy
    guard traces it to an owner without denormalising the organization
    onto every row.
    """

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE,
                                 related_name="events",
                                 verbose_name=_("campaign"))
    kind = models.CharField(_("kind"), max_length=20,
                            choices=CampaignEventKind.choices,
                            default=CampaignEventKind.NOTE)
    body = models.TextField(_("detail"), blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="campaign_events", verbose_name=_("by"),
    )
    is_internal = models.BooleanField(
        _("internal"), default=True,
        help_text=_("Internal entries are never shown to the client."),
    )

    class Meta:
        verbose_name = _("campaign history entry")
        verbose_name_plural = _("campaign history")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["campaign", "-created_at"],
                         name="campaignevent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.campaign_id}: {self.get_kind_display()}"
