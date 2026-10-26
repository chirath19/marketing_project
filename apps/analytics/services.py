"""Manual report drafts and explicit client publication."""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.analytics.models import ClientReport
from apps.messaging.policies import may_access
from apps.notifications.services import notify


@transaction.atomic
def create_report(*, actor, organization, client, publish=False, attachment=None, **values):
    if not may_access(actor, organization, client, "analytics_create") or not actor.is_staff_member:
        raise PermissionDenied
    report = ClientReport(organization=organization, client=client, created_by=actor, **values)
    if publish:
        report.published_at = timezone.now()
    from apps.messaging.references import validate

    validate(
        actor=actor, organization=organization, client=client, subscription=report.subscription
    )
    report.full_clean()
    report.save()
    if attachment:
        add_attachment(actor=actor, report=report, upload=attachment)
    if publish:
        _notify(report)
    return report


@transaction.atomic
def publish_report(*, actor, report):
    report = ClientReport.objects.select_for_update().get(pk=report.pk)
    if not actor.is_staff_member or not may_access(
        actor, report.organization, report.client, "analytics_edit"
    ):
        raise PermissionDenied
    if not report.published_at:
        report.published_at = timezone.now()
        report.save(update_fields=["published_at", "updated_at"])
        _notify(report)
    return report


@transaction.atomic
def update_report(*, actor, report, publish=False, attachment=None, **values):
    report = ClientReport.objects.select_for_update().get(pk=report.pk)
    if not actor.is_staff_member or not may_access(
        actor, report.organization, report.client, "analytics_edit"
    ):
        raise PermissionDenied
    allowed = {"title", "summary", "next_steps", "progress", "status", "subscription",
               "milestones", "completed_work"}
    if values.keys() - allowed:
        raise PermissionDenied
    from apps.messaging.references import validate

    for key, value in values.items():
        setattr(report, key, value)
    validate(actor=actor, organization=report.organization, client=report.client,
             subscription=report.subscription)
    first_publication = publish and not report.published_at
    if first_publication:
        report.published_at = timezone.now()
    report.full_clean()
    report.save()
    if attachment:
        add_attachment(actor=actor, report=report, upload=attachment)
    if first_publication:
        _notify(report)
    return report


def _notify(report):
    notify(
        recipient=report.client,
        title="A progress report is ready",
        body=report.title,
        url=reverse("organizations:client_reports"),
        category="reports",
    )


@transaction.atomic
def add_attachment(*, actor, report, upload):
    from pathlib import Path

    from django.core.exceptions import ValidationError

    from apps.analytics.models import ReportAttachment

    report = ClientReport.objects.select_for_update().get(pk=report.pk)
    if not actor.is_staff_member or not may_access(
        actor, report.organization, report.client, "analytics_create"
    ):
        raise PermissionDenied
    if upload.size > 5 * 1024 * 1024 or report.attachments.count() >= 10:
        raise ValidationError("Use up to ten attachments, no larger than 5 MB each.")
    data = upload.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise ValidationError("Attachments must be no larger than 5 MB.")
    suffix = Path(upload.name).suffix.lower()
    signatures = {
        ".pdf": (b"%PDF-", "application/pdf"),
        ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
        ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
        ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
    }
    if suffix not in signatures or not data.startswith(signatures[suffix][0]):
        raise ValidationError("Upload a PDF, PNG or JPEG document.")
    return ReportAttachment.objects.create(
        report=report,
        name=Path(upload.name).name[:200],
        data=data,
        size=len(data),
        content_type=signatures[suffix][1],
    )
