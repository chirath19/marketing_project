"""Shared client decisions, append-only discussion and transition history."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.organizations.models import OrganizationOwnedModel


class ApprovalRequest(OrganizationOwnedModel, TimeStampedModel, UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        CHANGES = "changes_requested", "Changes requested"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.PROTECT, related_name="approval_requests"
    )
    social_review = models.OneToOneField(
        "social.SocialApproval",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_request",
    )
    email_review = models.OneToOneField(
        "email_marketing.EmailApproval",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_request",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approval_requests_created"
    )
    requested_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    client_response = models.TextField(blank=True, max_length=5000)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_requests_resolved",
    )

    class Meta:
        ordering = ["-requested_at", "pk"]
        indexes = [
            models.Index(
                fields=["organization", "status", "requested_at"], name="approval_pending_idx"
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(social_review__isnull=True)
                | models.Q(email_review__isnull=True),
                name="approval_one_source",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="pending", resolved_at__isnull=True)
                    | (~models.Q(status="pending") & models.Q(resolved_at__isnull=False))
                ),
                name="approval_resolution_time",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["pending", "approved", "changes_requested", "rejected", "cancelled"]
                ),
                name="approval_valid_status",
            ),
        ]

    def clean(self):
        if self.campaign_id and self.campaign.organization_id != self.organization_id:
            raise ValidationError({"campaign": "Choose a campaign belonging to this client."})
        for field in ("social_review", "email_review"):
            if getattr(self, f"{field}_id"):
                review = getattr(self, field)
                parent = (
                    review.deliverable.content
                    if field == "social_review"
                    else review.deliverable.work
                )
                if (
                    review.organization_id != self.organization_id
                    or parent.campaign_id != self.campaign_id
                ):
                    raise ValidationError(
                        {field: "The review must belong to this client and campaign."}
                    )

    @property
    def source_module(self):
        if self.social_review_id:
            return "social"
        if self.email_review_id:
            return "email_marketing"
        return ""

    def __str__(self):
        return self.title


class ApprovalComment(TimeStampedModel):
    request = models.ForeignKey(ApprovalRequest, on_delete=models.PROTECT, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField(max_length=5000)

    class Meta:
        ordering = ["created_at", "pk"]


class ApprovalHistory(models.Model):
    class Kind(models.TextChoices):
        REQUESTED = "requested", "Requested"
        DECIDED = "decided", "Client decision"
        CANCELLED = "cancelled", "Cancelled"
        COMMENTED = "commented", "Comment added"

    request = models.ForeignKey(ApprovalRequest, on_delete=models.PROTECT, related_name="history")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    created_at = models.DateTimeField(default=timezone.now)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    detail = models.TextField(blank=True)
    comment = models.OneToOneField(ApprovalComment, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.request_id}: {self.kind} at {self.created_at}"
