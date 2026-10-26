"""Authorized writes. Lock the content parent before any child or review change."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.approvals import services as approval_services
from apps.core.events import DomainEvent, bus
from apps.social import policies
from apps.social.models import (
    METRICS,
    ContentItem,
    CreatorPartnership,
    SocialApproval,
    SocialChannel,
    SocialDeliverable,
    SocialMetric,
)


def _authorize(actor, organization, action):
    if not policies.can_write(actor, organization, action):
        raise PermissionDenied("You do not have access to change this client's social work.")


def _assign(record, values, allowed):
    if set(values) - set(allowed):
        raise ValidationError("Unsupported fields.")
    for key, value in values.items():
        setattr(record, key, value)


def _saved(record, actor, name):
    record.full_clean()
    record.save()
    bus.publish(
        DomainEvent(
            f"social.{name}",
            {"organization_id": record.organization_id, "id": str(record.pk), "actor_id": actor.pk},
        )
    )
    return record


def _content(organization, content):
    return ContentItem.objects.select_for_update().get(pk=content.pk, organization=organization)


def _draft_only(content):
    if content.status == ContentItem.Status.PUBLISHED:
        raise ValidationError(
            "Published work is preserved. Create a new content item for a new version."
        )


def _invalidate(content, actor):
    approval_services.cancel_source_reviews(
        reviews=SocialApproval.objects.filter(deliverable__content=content),
        actor=actor,
    )
    if content.status == ContentItem.Status.SCHEDULED:
        content.status = ContentItem.Status.DRAFT


@transaction.atomic
def save_channel(*, actor, organization, channel=None, **values):
    _authorize(actor, organization, "edit" if channel else "create")
    record = (
        SocialChannel.objects.select_for_update().get(pk=channel.pk, organization=organization)
        if channel
        else SocialChannel(organization=organization)
    )
    if (
        channel
        and record.content_items.exists()
        and any(
            getattr(record, key) != value for key, value in values.items() if key != "is_active"
        )
    ):
        raise ValidationError(
            "This channel has content. Create a new channel to change its identity."
        )
    _assign(record, values, ("name", "platform", "handle", "profile_url", "is_active"))
    return _saved(record, actor, "channel_saved")


@transaction.atomic
def save_partnership(*, actor, organization, partnership=None, **values):
    _authorize(actor, organization, "edit" if partnership else "create")
    record = (
        CreatorPartnership.objects.select_for_update().get(
            pk=partnership.pk, organization=organization
        )
        if partnership
        else CreatorPartnership(organization=organization)
    )
    if (
        partnership
        and record.content_items.exists()
        and values.get("campaign", record.campaign).pk != record.campaign_id
    ):
        raise ValidationError("A partnership with content cannot move to another campaign.")
    _assign(
        record,
        values,
        (
            "campaign",
            "creator_name",
            "platform",
            "profile_url",
            "brief",
            "internal_notes",
            "status",
            "due_on",
            "client_visible",
        ),
    )
    return _saved(record, actor, "partnership_saved")


@transaction.atomic
def save_content(*, actor, organization, content=None, expected_revision=None, **values):
    _authorize(actor, organization, "edit" if content else "create")
    record = _content(organization, content) if content else ContentItem(organization=organization)
    if content:
        if expected_revision != record.revision:
            raise ValidationError("This item changed. Reload it before saving.")
        for key in ("campaign", "channel", "partnership"):
            if key in values and getattr(values[key], "pk", None) != getattr(record, f"{key}_id"):
                raise ValidationError(
                    "Existing content cannot move to a different campaign, channel or partnership."
                )
        review_changed = any(
            getattr(record, key) != value
            for key, value in values.items()
            if key != "internal_notes"
        )
        if review_changed:
            _draft_only(record)
            _invalidate(record, actor)
            record.revision += 1
    _assign(
        record,
        values,
        (
            "campaign",
            "channel",
            "partnership",
            "title",
            "kind",
            "caption",
            "internal_notes",
            "scheduled_at",
            "client_visible",
        ),
    )
    record.channel = SocialChannel.objects.select_for_update().get(pk=record.channel_id)
    if record.partnership_id:
        record.partnership = CreatorPartnership.objects.select_for_update().get(
            pk=record.partnership_id
        )
    if not record.channel.is_active and not content:
        raise ValidationError("Choose an active channel.")
    return _saved(record, actor, "content_saved")


@transaction.atomic
def save_deliverable(
    *, actor, organization, content, deliverable=None, expected_revision=None, **values
):
    _authorize(actor, organization, "edit" if deliverable else "create")
    parent = _content(organization, content)
    _draft_only(parent)
    record = (
        SocialDeliverable.objects.select_for_update().get(
            pk=deliverable.pk, organization=organization, content=parent
        )
        if deliverable
        else SocialDeliverable(organization=organization, content=parent)
    )
    if deliverable:
        if expected_revision != record.revision:
            raise ValidationError("This deliverable changed. Reload it before saving.")
        if any(getattr(record, key) != value for key, value in values.items()):
            record.revision += 1
            approval_services.cancel_source_reviews(reviews=record.approvals.all(), actor=actor)
    _assign(
        record,
        values,
        ("title", "description", "asset_url", "due_on", "client_visible", "approval_required"),
    )
    # Any delivery change returns a schedule to draft for staff to validate again.
    if parent.status == ContentItem.Status.SCHEDULED:
        parent.status = ContentItem.Status.DRAFT
        parent.save(update_fields=["status", "updated_at"])
    return _saved(record, actor, "deliverable_saved")


def _approved(deliverable, content):
    return deliverable.approvals.filter(
        status="approved",
        deliverable_revision=deliverable.revision,
        content_revision=content.revision,
    ).exists()


@transaction.atomic
def request_review(*, actor, organization, deliverable):
    _authorize(actor, organization, "edit")
    parent = _content(organization, deliverable.content)
    _draft_only(parent)
    record = SocialDeliverable.objects.select_for_update().get(
        pk=deliverable.pk, organization=organization, content=parent
    )
    if (
        parent.status == ContentItem.Status.CANCELLED
        or not parent.client_visible
        or not record.client_visible
    ):
        raise ValidationError(
            "Share the content and deliverable with the client before requesting review."
        )
    if not record.description.strip() and not record.asset_url:
        raise ValidationError("Provide reviewable content or an asset link first.")
    if record.approvals.filter(status="pending").exists() or _approved(record, parent):
        raise ValidationError("This revision already has a pending review or an approval.")
    review = SocialApproval(
        organization=organization,
        deliverable=record,
        requested_by=actor,
        deliverable_revision=record.revision,
        content_revision=parent.revision,
        snapshot={
            "title": record.title,
            "description": record.description,
            "asset_url": record.asset_url,
            "content_title": parent.title,
            "caption": parent.caption,
            "kind": parent.get_kind_display(),
            "channel": str(parent.channel),
            "scheduled_at": parent.scheduled_at.isoformat() if parent.scheduled_at else "",
        },
    )
    _saved(review, actor, "review_requested")
    approval_services.register_review(review=review, actor=actor)
    return review


@transaction.atomic
def decide_review(*, actor, organization, approval, decision, feedback=""):
    reference = SocialApproval.objects.get(pk=approval.pk, organization=organization)
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
def change_status(*, actor, organization, content, status, published_at=None, published_url=""):
    _authorize(actor, organization, "edit")
    parent = _content(organization, content)
    _draft_only(parent)
    if status not in ContentItem.Status.values:
        raise ValidationError("Choose a valid status.")
    if status in {"scheduled", "published"}:
        if not parent.channel.is_active:
            raise ValidationError(
                "Activate the channel before scheduling or recording publication."
            )
        required = parent.deliverables.filter(approval_required=True)
        if any(not _approved(delivery, parent) for delivery in required):
            raise ValidationError(
                "All required deliverables need client approval for their current revision."
            )
    if status == "published":
        _authorize(actor, organization, "publish")
        parent.published_at, parent.published_url = published_at, published_url
    if status == "cancelled":
        _invalidate(parent, actor)
    parent.status = status
    return _saved(parent, actor, "status_changed")


@transaction.atomic
def record_metrics(*, actor, organization, content, date, source, **values):
    _authorize(actor, organization, "create")
    parent = _content(organization, content)
    if set(values) != set(METRICS):
        raise ValidationError("Supply every daily measure; use zero only for a measured zero.")
    for value in values.values():
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or number != number.to_integral_value():
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError("Metrics must be nonnegative whole numbers.") from None
    record = SocialMetric.objects.filter(content=parent, date=date).first()
    if record:
        _authorize(actor, organization, "edit")
    else:
        record = SocialMetric(organization=organization, content=parent, date=date)
    _assign(record, values, METRICS)
    record.source, record.recorded_by = source, actor
    return _saved(record, actor, "metrics_recorded")
