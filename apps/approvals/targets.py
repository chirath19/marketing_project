"""Adapters preserve domain revisions while the shared request owns the decision."""

from django.core.exceptions import ValidationError

from apps.email_marketing.models import EmailApproval, EmailWorkItem
from apps.social.models import ContentItem, SocialApproval


def lock_source(request):
    # Lock order matches source services: work/content, legacy review, shared request.
    if request.social_review_id:
        ref = SocialApproval.objects.get(pk=request.social_review_id)
        parent = ContentItem.objects.select_for_update().get(pk=ref.deliverable.content_id)
        review = SocialApproval.objects.select_for_update().get(pk=ref.pk)
        return parent, review
    if request.email_review_id:
        ref = EmailApproval.objects.get(pk=request.email_review_id)
        parent = EmailWorkItem.objects.select_for_update().get(pk=ref.deliverable.work_id)
        review = EmailApproval.objects.select_for_update().get(pk=ref.pk)
        return parent, review
    return None, None


def validate_current(parent, review):
    if review is None:
        return
    revision = (
        review.content_revision if isinstance(review, SocialApproval) else review.work_revision
    )
    if (
        review.status != "pending"
        or parent.status == "cancelled"
        or revision != parent.revision
        or review.deliverable_revision != review.deliverable.revision
    ):
        raise ValidationError("This review is no longer current. Reload the deliverable.")


def sync_decision(review, request):
    if review is None:
        return
    review.status = request.status
    if request.status != "cancelled":
        review.feedback = request.client_response
        review.decided_by = request.resolved_by
        review.decided_at = request.resolved_at
    review.full_clean()
    review.save()
