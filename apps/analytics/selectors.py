from apps.analytics.models import ClientReport
from apps.messaging.policies import may_access


def client_reports(actor, organization, client):
    rows = ClientReport.objects.filter(organization=organization, client=client)
    if not may_access(actor, organization, client, "analytics_view"):
        return rows.none()
    if not actor.is_staff_member:
        rows = rows.filter(published_at__isnull=False)
    return rows.select_related("created_by", "subscription").prefetch_related("attachments")


def attachment_for(actor, pk, organization=None):
    from apps.analytics.models import ReportAttachment

    attachment = (
        ReportAttachment.objects.select_related("report__organization", "report__client")
        .filter(pk=pk)
        .first()
    )
    if not attachment:
        return None
    report = attachment.report
    if not actor.is_staff_member and getattr(organization, "pk", None) != report.organization_id:
        return None
    if not client_reports(actor, report.organization, report.client).filter(pk=report.pk).exists():
        return None
    return attachment
