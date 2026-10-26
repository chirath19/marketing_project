"""Client email-service records only. These models never send or queue email."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import OrganizationOwnedModel

METRICS = ("recipients", "opens", "clicks", "conversions")
WEB_URL = URLValidator(schemes=["http", "https"])


def same_organization(record, field):
    if (
        getattr(record, f"{field}_id", None)
        and getattr(record, field).organization_id != record.organization_id
    ):
        raise ValidationError({field: "Choose a record belonging to this client."})


class EmailWorkItem(OrganizationOwnedModel, TimeStampedModel, UUIDPrimaryKeyModel):
    """Typed email work below the shared campaign, not a parallel campaign engine."""

    class Kind(models.TextChoices):
        CAMPAIGN = "campaign", "Email campaign"
        NEWSLETTER = "newsletter", "Newsletter"
        AUTOMATION = "automation", "Automation flow"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_PROGRESS = "in_progress", "In progress"
        SCHEDULED = "scheduled", "Scheduled externally (planned)"
        ACTIVE = "active", "Active externally (recorded)"
        COMPLETED = "completed", "Completed externally (recorded)"
        CANCELLED = "cancelled", "Cancelled"

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.PROTECT, related_name="email_work"
    )
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    subject = models.CharField(max_length=250, blank=True)
    brief = models.TextField(
        blank=True,
        help_text="Client-facing copy, plan or flow description. HTML is displayed as text.",
    )
    audience_description = models.CharField(
        max_length=250,
        blank=True,
        help_text="Describe the segment; do not upload recipient addresses.",
    )
    audience_size = models.PositiveBigIntegerField(
        null=True, blank=True, help_text="Planned audience size. Leave blank if unknown."
    )
    trigger_description = models.TextField(
        blank=True,
        help_text=(
            "For automation flows: the trigger, steps and exit conditions. Documentation only."
        ),
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual external send or flow start time, recorded by staff.",
    )
    execution_note = models.CharField(
        max_length=250,
        blank=True,
        help_text="Reference or explanation of the work performed externally.",
    )
    result_summary = models.TextField(
        blank=True, help_text="Client-facing interpretation of recorded results."
    )
    internal_notes = models.TextField(blank=True)
    client_visible = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        ordering = [models.F("scheduled_at").asc(nulls_last=True), "-created_at", "pk"]
        indexes = [
            models.Index(
                fields=["organization", "status", "scheduled_at"], name="email_work_schedule_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="scheduled") | models.Q(scheduled_at__isnull=False),
                name="email_scheduled_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(status__in=["active", "completed"])
                | (models.Q(executed_at__isnull=False) & ~models.Q(execution_note="")),
                name="email_execution_evidence",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="active") | models.Q(kind="automation"),
                name="email_active_flow_only",
            ),
        ]

    def clean(self):
        same_organization(self, "campaign")
        if self.campaign_id and self.campaign.service_type != "email_marketing":
            raise ValidationError({"campaign": "Choose an Email Marketing campaign."})
        if self.status == self.Status.SCHEDULED and not self.scheduled_at:
            raise ValidationError({"scheduled_at": "A schedule needs a date and time."})
        if self.status == self.Status.ACTIVE and self.kind != self.Kind.AUTOMATION:
            raise ValidationError({"status": "Only an automation flow can be active externally."})
        if self.status in {self.Status.ACTIVE, self.Status.COMPLETED} and (
            not self.executed_at or not self.execution_note.strip()
        ):
            raise ValidationError("Record the actual external execution time and a reference.")
        if self.executed_at and self.executed_at > timezone.now():
            raise ValidationError({"executed_at": "External execution cannot be in the future."})

    def __str__(self):
        return self.name


class EmailDeliverable(OrganizationOwnedModel, TimeStampedModel, UUIDPrimaryKeyModel):
    work = models.ForeignKey(EmailWorkItem, on_delete=models.PROTECT, related_name="deliverables")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    asset_url = models.URLField(
        blank=True,
        validators=[WEB_URL],
        help_text=(
            "External preview or document link. "
            "Use a version-specific URL with suitable sharing permissions."
        ),
    )
    due_on = models.DateField(null=True, blank=True)
    client_visible = models.BooleanField(default=False)
    approval_required = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        ordering = ["due_on", "created_at", "pk"]

    def clean(self):
        same_organization(self, "work")

    def __str__(self):
        return self.name


class EmailApproval(OrganizationOwnedModel, TimeStampedModel, UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting review"
        APPROVED = "approved", "Approved"
        CHANGES = "changes_requested", "Changes requested"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Superseded / cancelled"

    deliverable = models.ForeignKey(
        EmailDeliverable, on_delete=models.PROTECT, related_name="approvals"
    )
    deliverable_revision = models.PositiveIntegerField()
    work_revision = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="email_reviews_requested"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="email_reviews_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["deliverable"],
                condition=models.Q(status="pending"),
                name="email_one_pending_review",
            )
        ]

    def clean(self):
        same_organization(self, "deliverable")


class EmailMetric(OrganizationOwnedModel, TimeStampedModel):
    """Daily event counts from an external report; not cumulative or unique-audience totals."""

    work = models.ForeignKey(EmailWorkItem, on_delete=models.PROTECT, related_name="metrics")
    date = models.DateField()
    recipients = models.PositiveBigIntegerField(
        help_text="Recipient deliveries for this day, not the planned list size."
    )
    opens = models.PositiveBigIntegerField(
        help_text="Open events recorded that day, including repeat opens."
    )
    clicks = models.PositiveBigIntegerField()
    conversions = models.PositiveBigIntegerField()
    source = models.CharField(
        max_length=200, help_text="The external report used for these observations."
    )
    result_summary = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["work", "date"], name="email_metric_daily_unique")
        ]
        indexes = [models.Index(fields=["organization", "date"], name="email_metric_date_idx")]

    def clean(self):
        same_organization(self, "work")
        if self.date and self.date > timezone.localdate():
            raise ValidationError({"date": "Observed results cannot be in the future."})
        if self.work_id:
            if not self.work.executed_at:
                raise ValidationError("Record external execution before entering results.")
            if self.date and self.date < timezone.localtime(self.work.executed_at).date():
                raise ValidationError({"date": "Results cannot precede external execution."})
