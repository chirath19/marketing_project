"""Social planning, dated observations and revision-specific client reviews."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import OrganizationOwnedModel

WEB_URL = URLValidator(schemes=["https", "http"])
METRICS = ("impressions", "views", "likes", "comments", "shares", "saves", "clicks", "leads")


class Platform(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    FACEBOOK = "facebook", "Facebook"
    LINKEDIN = "linkedin", "LinkedIn"
    TIKTOK = "tiktok", "TikTok"
    YOUTUBE = "youtube", "YouTube"
    X = "x", "X"
    OTHER = "other", "Other"


def same_organization(instance, field):
    if getattr(instance, f"{field}_id", None):
        related = getattr(instance, field)
        if related.organization_id != instance.organization_id:
            raise ValidationError({field: "Choose a record belonging to this client."})


def social_campaign(instance):
    same_organization(instance, "campaign")
    if instance.campaign_id and instance.campaign.service_type != "social":
        raise ValidationError({"campaign": "Choose a Social Media campaign."})


class SocialChannel(OrganizationOwnedModel, TimeStampedModel):
    name = models.CharField(max_length=150)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    handle = models.CharField(max_length=150, blank=True)
    profile_url = models.URLField(blank=True, validators=[WEB_URL])
    external_id = models.CharField(max_length=200, blank=True, editable=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="social_channel_name")
        ]

    def __str__(self):
        return f"{self.name} ({self.get_platform_display()})"


class CreatorPartnership(OrganizationOwnedModel, TimeStampedModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.PROTECT, related_name="creator_partnerships"
    )
    creator_name = models.CharField(max_length=150)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    profile_url = models.URLField(blank=True, validators=[WEB_URL])
    brief = models.TextField(blank=True, help_text="Client-facing partnership brief.")
    internal_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    due_on = models.DateField(null=True, blank=True)
    client_visible = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "pk"]

    def clean(self):
        social_campaign(self)

    def __str__(self):
        return self.creator_name


class ContentItem(OrganizationOwnedModel, TimeStampedModel, UUIDPrimaryKeyModel):
    class Kind(models.TextChoices):
        POST = "post", "Post"
        REEL = "reel", "Short video / reel"
        VIDEO = "video", "Video"
        STORY = "story", "Story"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled (manual posting)"
        PUBLISHED = "published", "Published (recorded manually)"
        CANCELLED = "cancelled", "Cancelled"

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.PROTECT, related_name="social_content"
    )
    channel = models.ForeignKey(
        SocialChannel, on_delete=models.PROTECT, related_name="content_items"
    )
    partnership = models.ForeignKey(
        CreatorPartnership,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="content_items",
    )
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.POST)
    caption = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    published_url = models.URLField(blank=True, validators=[WEB_URL])
    client_visible = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1, editable=False)
    external_id = models.CharField(max_length=200, blank=True, editable=False)

    class Meta:
        ordering = [models.F("scheduled_at").asc(nulls_last=True), "-created_at", "pk"]
        indexes = [
            models.Index(
                fields=["organization", "status", "scheduled_at"], name="social_schedule_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status="scheduled") | models.Q(scheduled_at__isnull=False),
                name="social_scheduled_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="published")
                | (models.Q(published_at__isnull=False) & ~models.Q(published_url="")),
                name="social_publication_record",
            ),
        ]

    def clean(self):
        social_campaign(self)
        same_organization(self, "channel")
        same_organization(self, "partnership")
        if self.partnership_id and self.partnership.campaign_id != self.campaign_id:
            raise ValidationError({"partnership": "The partnership must belong to this campaign."})
        if self.status == self.Status.SCHEDULED and not self.scheduled_at:
            raise ValidationError({"scheduled_at": "A scheduled item needs a date and time."})
        if self.status == self.Status.PUBLISHED and (
            not self.published_at or not self.published_url
        ):
            raise ValidationError("Record the publication date and public post URL.")
        if self.published_at and self.published_at > timezone.now():
            raise ValidationError({"published_at": "Publication cannot be in the future."})

    def __str__(self):
        return self.title


class SocialDeliverable(OrganizationOwnedModel, TimeStampedModel, UUIDPrimaryKeyModel):
    content = models.ForeignKey(ContentItem, on_delete=models.PROTECT, related_name="deliverables")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    asset_url = models.URLField(
        blank=True,
        validators=[WEB_URL],
        help_text=(
            "A reviewable HTTPS/HTTP link. Check the file's sharing permissions before sharing."
        ),
    )
    due_on = models.DateField(null=True, blank=True)
    client_visible = models.BooleanField(default=False)
    approval_required = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        ordering = ["due_on", "created_at", "pk"]

    def clean(self):
        same_organization(self, "content")

    def __str__(self):
        return self.title


class SocialApproval(OrganizationOwnedModel, TimeStampedModel, UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting review"
        APPROVED = "approved", "Approved"
        CHANGES = "changes_requested", "Changes requested"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Superseded / cancelled"

    deliverable = models.ForeignKey(
        SocialDeliverable, on_delete=models.PROTECT, related_name="approvals"
    )
    deliverable_revision = models.PositiveIntegerField()
    content_revision = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="social_reviews_requested"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="social_reviews_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["deliverable"],
                condition=models.Q(status="pending"),
                name="social_one_pending_review",
            )
        ]

    def clean(self):
        same_organization(self, "deliverable")


class SocialMetric(OrganizationOwnedModel, TimeStampedModel):
    """Daily increments, not cumulative lifetime totals; missing observations stay absent."""

    content = models.ForeignKey(ContentItem, on_delete=models.PROTECT, related_name="metrics")
    date = models.DateField()
    impressions = models.PositiveBigIntegerField()
    views = models.PositiveBigIntegerField()
    likes = models.PositiveBigIntegerField()
    comments = models.PositiveBigIntegerField()
    shares = models.PositiveBigIntegerField()
    saves = models.PositiveBigIntegerField()
    clicks = models.PositiveBigIntegerField()
    leads = models.PositiveBigIntegerField()
    source = models.CharField(max_length=200)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    entry_method = models.CharField(max_length=20, default="manual", editable=False)

    class Meta:
        ordering = ["-date", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["content", "date"], name="social_metric_daily_unique")
        ]
        indexes = [models.Index(fields=["organization", "date"], name="social_metric_date_idx")]

    def clean(self):
        same_organization(self, "content")
        if self.date and self.date > timezone.localdate():
            raise ValidationError({"date": "Observed results cannot be in the future."})
        if self.content_id and self.content.status != ContentItem.Status.PUBLISHED:
            raise ValidationError({"content": "Record results for a published item."})
        if (
            self.date
            and self.content_id
            and self.content.published_at
            and self.date < timezone.localtime(self.content.published_at).date()
        ):
            raise ValidationError({"date": "Results cannot precede publication."})
