"""Transactional manual records and client reviews. No mail, provider or queue calls."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.approvals import services as approval_services
from apps.core.events import DomainEvent, bus
from apps.email_marketing import policies
from apps.email_marketing.models import (
    METRICS,
    EmailApproval,
    EmailDeliverable,
    EmailMetric,
    EmailWorkItem,
)

WORK_FIELDS = {
    "campaign",
    "name",
    "kind",
    "subject",
    "brief",
    "audience_description",
    "audience_size",
    "trigger_description",
    "scheduled_at",
    "result_summary",
    "internal_notes",
    "client_visible",
}
DELIVERY_FIELDS = {
    "name",
    "description",
    "asset_url",
    "due_on",
    "client_visible",
    "approval_required",
}
REPORT_FIELDS = {"result_summary", "internal_notes"}
TRANSITIONS = {
    "draft": {"in_progress", "scheduled", "active", "completed", "cancelled"},
    "in_progress": {"draft", "scheduled", "active", "completed", "cancelled"},
    "scheduled": {"draft", "in_progress", "active", "completed", "cancelled"},
    "active": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _authorize(actor, organization, action):
    if not policies.can_write(actor, organization, action):
        raise PermissionDenied("You cannot change this client's email marketing work.")


def _fields(values, allowed):
    if set(values) - allowed:
        raise ValidationError("Unsupported fields.")


def _assign(record, values):
    for field, value in values.items():
        setattr(record, field, value)


def _whole_number(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Audience and metrics must be nonnegative whole numbers.") from None


def _saved(record, actor, event):
    record.full_clean()
    record.save()
    bus.publish(
        DomainEvent(
            f"email_marketing.{event}",
            {"organization_id": record.organization_id, "id": str(record.pk), "actor_id": actor.pk},
        )
    )
    return record


def _work(organization, work):
    return EmailWorkItem.objects.select_for_update().get(pk=work.pk, organization=organization)


def _editable(work):
    if work.executed_at or work.status in {"completed", "cancelled"}:
        raise ValidationError(
            "Executed or cancelled work is preserved. Create a new work item for a new version."
        )


def _invalidate(work, actor):
    approval_services.cancel_source_reviews(
        reviews=EmailApproval.objects.filter(deliverable__work=work),
        actor=actor,
    )
    if work.status == "scheduled":
        work.status = "draft"


@transaction.atomic
def save_work(*, actor, organization, work=None, expected_revision=None, **values):
    _authorize(actor, organization, "edit" if work else "create")
    _fields(values, WORK_FIELDS)
    if values.get("audience_size") is not None:
        _whole_number(values["audience_size"])
    record = _work(organization, work) if work else EmailWorkItem(organization=organization)
    if work:
        if expected_revision != record.revision:
            raise ValidationError("This work changed. Reload it before saving.")
        if "campaign" in values and values["campaign"].pk != record.campaign_id:
            raise ValidationError("Existing work cannot move to another campaign.")
        changes = {key for key, value in values.items() if getattr(record, key) != value}
        if changes - REPORT_FIELDS:
            _editable(record)
            _invalidate(record, actor)
        # Reporting notes are outside the creative revision a client approves.
        if changes - REPORT_FIELDS:
            record.revision += 1
    _assign(record, values)
    return _saved(record, actor, "work_saved")


@transaction.atomic
def save_deliverable(
    *, actor, organization, work, deliverable=None, expected_revision=None, **values
):
    _authorize(actor, organization, "edit" if deliverable else "create")
    _fields(values, DELIVERY_FIELDS)
    parent = _work(organization, work)
    _editable(parent)
    record = (
        EmailDeliverable.objects.select_for_update().get(
            pk=deliverable.pk, organization=organization, work=parent
        )
        if deliverable
        else EmailDeliverable(organization=organization, work=parent)
    )
    changed = not deliverable or any(getattr(record, key) != value for key, value in values.items())
    if deliverable:
        if expected_revision != record.revision:
            raise ValidationError("This deliverable changed. Reload it before saving.")
        if changed:
            record.revision += 1
            approval_services.cancel_source_reviews(reviews=record.approvals.all(), actor=actor)
    _assign(record, values)
    if changed and parent.status == "scheduled":
        parent.status = "draft"
        parent.save(update_fields=["status", "updated_at"])
    return _saved(record, actor, "deliverable_saved")


def _approved(deliverable, work):
    return deliverable.approvals.filter(
        status="approved", deliverable_revision=deliverable.revision, work_revision=work.revision
    ).exists()


@transaction.atomic
def request_review(*, actor, organization, deliverable):
    _authorize(actor, organization, "edit")
    parent = _work(organization, deliverable.work)
    _editable(parent)
    record = EmailDeliverable.objects.select_for_update().get(
        pk=deliverable.pk, organization=organization, work=parent
    )
    if not parent.client_visible or not record.client_visible:
        raise ValidationError("Share both the work and deliverable before requesting review.")
    if not record.description.strip() and not record.asset_url:
        raise ValidationError("Provide reviewable content or a preview link.")
    if record.approvals.filter(status="pending").exists() or _approved(record, parent):
        raise ValidationError("This revision already has a pending review or approval.")
    review = EmailApproval(
        organization=organization,
        deliverable=record,
        requested_by=actor,
        deliverable_revision=record.revision,
        work_revision=parent.revision,
        snapshot={
            "name": record.name,
            "description": record.description,
            "asset_url": record.asset_url,
            "work_name": parent.name,
            "kind": parent.get_kind_display(),
            "subject": parent.subject,
            "brief": parent.brief,
            "audience_description": parent.audience_description,
            "audience_size": parent.audience_size,
            "trigger_description": parent.trigger_description,
            "scheduled_at": parent.scheduled_at.isoformat() if parent.scheduled_at else "",
        },
    )
    _saved(review, actor, "review_requested")
    approval_services.register_review(review=review, actor=actor)
    return review


@transaction.atomic
def decide_review(*, actor, organization, approval, decision, feedback=""):
    reference = EmailApproval.objects.get(pk=approval.pk, organization=organization)
    approval_services.decide(
        actor=actor,
        organization=organization,
        request=reference.approval_request,
        decision=decision,
        response=feedback,
    )
    reference.refresh_from_db()
    return reference


@transaction.atomic
def change_status(*, actor, organization, work, status, executed_at=None, execution_note=""):
    _authorize(actor, organization, "edit")
    parent = _work(organization, work)
    if status not in TRANSITIONS.get(parent.status, set()):
        raise ValidationError("That status transition is not available.")
    if status in {"scheduled", "active", "completed"} and any(
        not _approved(delivery, parent)
        for delivery in parent.deliverables.filter(approval_required=True)
    ):
        raise ValidationError("All required deliverables need approval for their current revision.")
    if status in {"active", "completed"}:
        # Existing publishing permission means recording external execution, never sending.
        _authorize(actor, organization, "publish")
        if not parent.executed_at:
            parent.executed_at, parent.execution_note = executed_at, execution_note.strip()
    if status == "cancelled":
        _invalidate(parent, actor)
    parent.status = status
    return _saved(parent, actor, "status_changed")


@transaction.atomic
def record_metrics(*, actor, organization, work, date, source, result_summary="", **values):
    _authorize(actor, organization, "create")
    parent = _work(organization, work)
    if set(values) != set(METRICS):
        raise ValidationError("Supply every daily measure; use zero only for a measured zero.")
    for value in values.values():
        _whole_number(value)
    record = EmailMetric.objects.filter(work=parent, date=date).first()
    if record:
        _authorize(actor, organization, "edit")
    else:
        record = EmailMetric(organization=organization, work=parent, date=date)
    _assign(record, values)
    record.source, record.recorded_by, record.result_summary = source, actor, result_summary
    return _saved(record, actor, "metrics_recorded")
