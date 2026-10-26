"""Manual progress reports. Available independently of automated analytics."""

from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from apps.core.models import TimeStampedModel
from apps.organizations.models import OrganizationOwnedModel


class ClientReport(OrganizationOwnedModel, TimeStampedModel):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="progress_reports"
    )
    subscription = models.ForeignKey("subscriptions.ClientSubscription", on_delete=models.PROTECT,
                                     null=True, blank=True, related_name="progress_reports")
    milestones = models.TextField(max_length=5000, blank=True)
    completed_work = models.TextField(max_length=5000, blank=True)
    title = models.CharField(max_length=200)
    summary = models.TextField(max_length=12000)
    next_steps = models.TextField(max_length=5000, blank=True)
    progress = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    status = models.CharField(
        max_length=20,
        choices=[
            ("planned", "Planned"),
            ("in_progress", "In progress"),
            ("waiting", "Waiting on client"),
            ("completed", "Completed"),
        ],
        default="in_progress",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-pk"]


class ReportAttachment(TimeStampedModel):
    """Small private documents; no public storage URL can bypass authorization."""

    report = models.ForeignKey(ClientReport, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)
    data = models.BinaryField()
    size = models.PositiveIntegerField()
