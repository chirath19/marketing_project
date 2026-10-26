"""Atomic approval transitions, history, comments and in-app notifications."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.approvals import notifications, policies, targets
from apps.approvals.models import ApprovalComment, ApprovalHistory, ApprovalRequest
from apps.core.events import DomainEvent, bus


def _history(request, actor, kind, previous="", detail="", comment=None):
    return ApprovalHistory.objects.create(
        request=request,
        actor=actor,
        kind=kind,
        from_status=previous,
        to_status=request.status,
        detail=detail,
        comment=comment,
    )


def _announce(request, actor, *, commented=False):
    notifications.changed(request, actor, commented=commented)
    bus.publish(
        DomainEvent(
            "approvals.commented" if commented else "approvals.changed",
            {
                "organization_id": request.organization_id,
                "request_id": str(request.pk),
                "status": request.status,
                "actor_id": actor.pk,
            },
        )
    )


@transaction.atomic
def create_request(*, actor, organization, campaign, title, description=""):
    if not policies.can_create(actor, organization):
        raise PermissionDenied("You cannot request approval for this client.")
    request = ApprovalRequest(
        organization=organization,
        campaign=campaign,
        title=title.strip(),
        description=description.strip(),
        requested_by=actor,
    )
    request.full_clean()
    request.save()
    _history(request, actor, "requested", detail="Client review requested.")
    _announce(request, actor)
    return request


def _source_policy(module):
    if module == "social":
        from apps.social import policies as source_policy
    elif module == "email_marketing":
        from apps.email_marketing import policies as source_policy
    else:
        raise ValidationError("Unsupported approval source.")
    return source_policy


@transaction.atomic
def register_review(*, review, actor):
    """Called inside the source's authorized, parent-locked request transaction."""
    module = review._meta.app_label
    if not _source_policy(module).can_write(actor, review.organization, "edit"):
        raise PermissionDenied("You cannot request review of this deliverable.")
    field = "social_review" if module == "social" else "email_review"
    existing = ApprovalRequest.objects.filter(**{field: review}).first()
    if existing:
        return existing
    parent = review.deliverable.content if module == "social" else review.deliverable.work
    request = ApprovalRequest(
        organization=review.organization,
        campaign=parent.campaign,
        **{field: review},
        title=review.deliverable.title if module == "social" else review.deliverable.name,
        description=review.deliverable.description,
        snapshot=review.snapshot,
        requested_by=review.requested_by,
        requested_at=review.created_at,
        status=review.status,
        client_response=review.feedback,
        resolved_at=(review.decided_at or review.updated_at)
        if review.status != "pending"
        else None,
        resolved_by=review.decided_by,
    )
    request.full_clean()
    request.save()
    _history(request, actor, "requested", detail="Deliverable version submitted for review.")
    _announce(request, actor)
    return request


def _locked(request, organization):
    reference = ApprovalRequest.objects.get(pk=request.pk, organization=organization)
    parent, review = targets.lock_source(reference)
    current = (
        ApprovalRequest.objects.select_for_update(of=("self",))
        .select_related(
            "organization",
            "campaign",
            "requested_by",
            "social_review__deliverable__content",
            "email_review__deliverable__work",
        )
        .get(pk=reference.pk, organization=organization)
    )
    return current, parent, review


@transaction.atomic
def decide(*, actor, organization, request, decision, response=""):
    current, parent, review = _locked(request, organization)
    if not policies.can_respond(actor, current):
        raise PermissionDenied("An authorized client member must respond to this request.")
    if current.status != "pending":
        raise ValidationError("This request has already been resolved. Refresh the page.")
    targets.validate_current(parent, review)
    if decision not in {"approved", "changes_requested", "rejected"}:
        raise ValidationError("Choose approve, request changes or reject.")
    response = response.strip()
    if decision in {"changes_requested", "rejected"} and not response:
        raise ValidationError("Explain the changes or the reason for rejection.")
    if len(response) > 5000:
        raise ValidationError("Keep your response within 5,000 characters.")
    current.status, current.client_response = decision, response
    current.resolved_at, current.resolved_by = timezone.now(), actor
    current.full_clean()
    current.save()
    targets.sync_decision(review, current)
    _history(current, actor, "decided", "pending", response)
    _announce(current, actor)
    if current.source_module:
        bus.publish(
            DomainEvent(
                f"{current.source_module}.review_decided",
                {
                    "organization_id": current.organization_id,
                    "id": str(review.pk),
                    "actor_id": actor.pk,
                },
            )
        )
    return current


def _cancel(current, review, actor, reason):
    if current.status != "pending":
        raise ValidationError("Only a pending request can be cancelled.")
    current.status, current.resolved_at, current.resolved_by = "cancelled", timezone.now(), actor
    current.full_clean()
    current.save()
    targets.sync_decision(review, current)
    _history(current, actor, "cancelled", "pending", reason)
    _announce(current, actor)
    return current


@transaction.atomic
def cancel(*, actor, organization, request, reason=""):
    current, _, review = _locked(request, organization)
    if not policies.can_cancel(actor, current):
        raise PermissionDenied("You cannot cancel this request.")
    if not reason.strip() or len(reason) > 5000:
        raise ValidationError("Provide a cancellation reason within 5,000 characters.")
    return _cancel(current, review, actor, reason.strip())


@transaction.atomic
def cancel_source_reviews(*, reviews, actor):
    """Source edit/cancel hooks; callers already hold their content/work parent lock."""
    for review in reviews.filter(status="pending"):
        if not _source_policy(review._meta.app_label).can_write(actor, review.organization, "edit"):
            raise PermissionDenied("You cannot revise this deliverable.")
        request = review.approval_request
        current, _, locked_review = _locked(request, review.organization)
        if current.status == "pending":
            _cancel(
                current, locked_review, actor, "The source work was revised, unshared or cancelled."
            )


@transaction.atomic
def add_comment(*, actor, organization, request, body):
    current, _, _ = _locked(request, organization)
    if not policies.can_comment(actor, current):
        raise PermissionDenied("You cannot comment on this approval.")
    # Discussion can continue after resolution, without reopening or changing the decision.
    body = body.strip()
    if len(body) > 5000:
        raise ValidationError("Keep your comment within 5,000 characters.")
    comment = ApprovalComment(request=current, author=actor, body=body)
    comment.full_clean()
    comment.save()
    _history(current, actor, "commented", current.status, comment=comment)
    _announce(current, actor, commented=True)
    return comment
