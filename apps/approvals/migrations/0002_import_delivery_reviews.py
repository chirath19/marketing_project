"""Preserve existing decisions without replaying notifications or domain events."""

from django.db import migrations


def import_reviews(apps, schema_editor):
    alias = schema_editor.connection.alias
    Request = apps.get_model("approvals", "ApprovalRequest")
    History = apps.get_model("approvals", "ApprovalHistory")
    for app_label, model_name, field, parent_name, title_key in [
        ("social", "SocialApproval", "social_review", "content", "title"),
        ("email_marketing", "EmailApproval", "email_review", "work", "name"),
    ]:
        Review = apps.get_model(app_label, model_name)
        for review in Review.objects.using(alias).select_related(
            f"deliverable__{parent_name}"
        ).iterator():
            delivery = review.deliverable
            parent = getattr(delivery, parent_name)
            snapshot = review.snapshot or {}
            request, created = Request.objects.using(alias).get_or_create(
                **{f"{field}_id": review.pk},
                defaults={
                    "organization_id": review.organization_id,
                    "campaign_id": parent.campaign_id,
                    "title": snapshot.get(title_key) or getattr(delivery, title_key),
                    "description": snapshot.get("description", delivery.description),
                    "snapshot": snapshot,
                    "requested_by_id": review.requested_by_id,
                    "requested_at": review.created_at,
                    "status": review.status,
                    "client_response": review.feedback,
                    "resolved_by_id": review.decided_by_id,
                    "resolved_at": (review.decided_at or review.updated_at)
                    if review.status != "pending" else None,
                },
            )
            if not created:
                continue
            History.objects.using(alias).create(
                request_id=request.pk, actor_id=review.requested_by_id,
                created_at=review.created_at, kind="requested", from_status="",
                to_status="pending", detail="Existing deliverable review imported.",
            )
            if review.status != "pending":
                History.objects.using(alias).create(
                    request_id=request.pk, actor_id=review.decided_by_id,
                    created_at=request.resolved_at,
                    kind="cancelled" if review.status == "cancelled" else "decided",
                    from_status="pending", to_status=review.status,
                    detail=review.feedback or "Existing resolution imported.",
                )


class Migration(migrations.Migration):
    dependencies = [("approvals", "0001_initial")]
    operations = [migrations.RunPython(import_reviews, migrations.RunPython.noop)]
