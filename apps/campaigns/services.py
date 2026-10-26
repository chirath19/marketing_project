"""Write operations for the Campaigns domain.

The only place a campaign changes. Every function authorises through
`policies.py` first, so the rule holds whether the caller is a staff
view, a future SEO module, an API or a management command.

Nothing here sends anything outbound. A campaign going live raises an
in-app notification for the client's own people; that is the whole
delivery mechanism, as everywhere else in this version.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.campaigns import policies
from apps.campaigns.models import (
    Campaign,
    CampaignEvent,
    CampaignEventKind,
    CampaignStatus,
)
from apps.core.events import DomainEvent, bus

logger = logging.getLogger(__name__)


#: Moves the lifecycle allows, declared as data so an unexpected one
#: raises rather than quietly rewriting what a client is being charged
#: for.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    CampaignStatus.PLANNED: frozenset({
        CampaignStatus.LIVE, CampaignStatus.CANCELLED,
    }),
    CampaignStatus.LIVE: frozenset({
        CampaignStatus.PAUSED, CampaignStatus.DONE, CampaignStatus.CANCELLED,
    }),
    CampaignStatus.PAUSED: frozenset({
        CampaignStatus.LIVE, CampaignStatus.DONE, CampaignStatus.CANCELLED,
    }),
    # Finished work can be restarted — a seasonal campaign that runs again
    # next year is the same campaign, and re-keying it loses its history.
    CampaignStatus.DONE: frozenset({CampaignStatus.LIVE}),
    # Cancelled is the dead end. It means the work was called off;
    # restarting it should be a deliberate new campaign, not a dropdown.
    CampaignStatus.CANCELLED: frozenset(),
}

#: Status changes the client is told about. Internal churn is not news;
#: their campaign going live or stopping is.
CLIENT_VISIBLE_STATUSES = frozenset({
    CampaignStatus.LIVE, CampaignStatus.PAUSED, CampaignStatus.DONE,
    CampaignStatus.CANCELLED,
})

#: Fields a caller may change through `update_campaign`. Everything else
#: — the client, the status, who is on it — has its own function, because
#: each is a different decision with a different right behind it.
EDITABLE_FIELDS = frozenset({
    "name", "description", "objective", "budget", "currency",
    "starts_on", "ends_on", "client_summary", "internal_notes",
    "subscription", "service_type",
})

#: Human names for the history entry, so a year later it reads as a
#: sentence rather than as a field dump.
FIELD_LABELS = {
    "name": "name", "description": "description", "objective": "objective",
    "budget": "budget", "currency": "currency", "starts_on": "start date",
    "ends_on": "end date", "client_summary": "summary for the client",
    "internal_notes": "internal notes", "subscription": "service",
    "service_type": "service area",
}


def _record(campaign: Campaign, *, kind: str, body: str, actor=None,  # noqa: ANN001
            is_internal: bool = True) -> CampaignEvent:
    return CampaignEvent.objects.create(
        campaign=campaign, kind=kind, body=body,
        actor=actor if getattr(actor, "pk", None) else None,
        is_internal=is_internal,
    )


@transaction.atomic
def create_campaign(*, organization, name: str, actor,  # noqa: ANN001
                    service_type: str = "", subscription=None,
                    status: str = CampaignStatus.PLANNED,
                    assignees=None, **fields) -> Campaign:
    """Start a campaign for a client.

    `service_type` is taken from the subscription when one is given and
    none was named, so the campaign lands in the right part of the
    client's workspace without anybody having to remember the mapping.
    """
    if not policies.can_create_campaigns(actor, organization):
        raise PermissionDenied("You may not create campaigns for this client.")

    if not service_type and subscription is not None:
        module = subscription.workspace_module
        service_type = module.key if module else ""

    if not policies.area_available(actor, service_type):
        raise PermissionDenied("This service workspace is disabled.")

    campaign = Campaign(
        organization=organization, subscription=subscription,
        service_type=service_type, name=name.strip(),
        status=status,
        owner=fields.pop("owner", None),
        **{key: value for key, value in fields.items() if key in EDITABLE_FIELDS},
    )
    # Validated rather than trusted: the service-area vocabulary, the
    # date ordering and the "same client as the subscription" rule are
    # model invariants, and a service function is one of the callers they
    # exist to protect against.
    campaign.full_clean(exclude=["assignees"])
    campaign.save()

    if assignees:
        campaign.assignees.set(assignees)

    if status == CampaignStatus.LIVE:
        campaign.started_at = timezone.now()
        campaign.save(update_fields=["started_at", "updated_at"])

    _record(campaign, kind=CampaignEventKind.CREATED, actor=actor,
            body=f"{campaign.name} created.", is_internal=False)

    bus.publish(DomainEvent("campaign.created", {
        "campaign_id": campaign.pk,
        "organization_id": organization.pk,
        "service_type": campaign.service_type,
        "status": status,
    }))

    if status == CampaignStatus.LIVE:
        _notify_client(campaign)

    logger.info("Campaign %s created for %s (%s)",
                campaign.pk, organization.slug, status)
    return campaign


@transaction.atomic
def change_status(*, campaign: Campaign, status: str, actor,  # noqa: ANN001
                  note: str = "") -> Campaign:
    """Move a campaign through its lifecycle."""
    if not policies.area_available(actor, campaign.service_type):
        raise PermissionDenied("This service workspace is disabled.")
    if not policies.can_change_status(actor, campaign.organization):
        raise PermissionDenied("You may not change this campaign's status.")

    if status not in CampaignStatus.values:
        raise ValidationError(f"{status!r} is not a campaign status.")

    if status == campaign.status:
        return campaign

    if status not in ALLOWED_TRANSITIONS.get(campaign.status, frozenset()):
        raise ValidationError(
            f"A {campaign.get_status_display().lower()} campaign cannot "
            f"become {CampaignStatus(status).label.lower()}."
        )

    previous = campaign.get_status_display()
    campaign.status = status
    updated = ["status", "updated_at"]

    if status == CampaignStatus.LIVE:
        if campaign.started_at is None:
            campaign.started_at = timezone.now()
            updated.append("started_at")
        if campaign.starts_on is None:
            campaign.starts_on = timezone.localdate()
            updated.append("starts_on")
        # Running again clears the end stamp; a lingering "ended" date
        # would contradict the status beside it.
        if campaign.ended_at is not None:
            campaign.ended_at = None
            updated.append("ended_at")
    elif status in {CampaignStatus.DONE, CampaignStatus.CANCELLED}:
        campaign.ended_at = timezone.now()
        updated.append("ended_at")

    campaign.save(update_fields=updated)

    _record(campaign, kind=CampaignEventKind.STATUS, actor=actor,
            body=f"{previous} → {campaign.get_status_display()}"
                 + (f". {note}" if note else ""),
            is_internal=status not in CLIENT_VISIBLE_STATUSES)

    bus.publish(DomainEvent("campaign.status_changed", {
        "campaign_id": campaign.pk,
        "organization_id": campaign.organization_id,
        "status": status,
    }))

    _notify_client(campaign)
    return campaign


@transaction.atomic
def update_campaign(*, campaign: Campaign, actor, **fields) -> Campaign:  # noqa: ANN001
    """Correct a campaign's detail."""
    if not policies.area_available(actor, fields.get("service_type", campaign.service_type)):
        raise PermissionDenied("This service workspace is disabled.")
    if not policies.area_available(actor, campaign.service_type):
        raise PermissionDenied("This service workspace is disabled.")
    if not policies.can_edit_campaigns(actor, campaign.organization):
        raise PermissionDenied("You may not change this campaign.")

    changed = []
    for field, value in fields.items():
        if field not in EDITABLE_FIELDS:
            continue
        if getattr(campaign, field) != value:
            setattr(campaign, field, value)
            changed.append(field)

    if not changed:
        return campaign

    campaign.full_clean(exclude=["assignees"])
    campaign.save(update_fields=[*changed, "updated_at"])

    summary = ", ".join(FIELD_LABELS.get(field, field) for field in changed)
    _record(campaign, kind=CampaignEventKind.UPDATED, actor=actor,
            body=f"Updated {summary}.",
            # A change to the client's own summary is a change they can
            # see, so saying so is not a leak.
            is_internal="client_summary" not in changed)

    return campaign


@transaction.atomic
def assign(*, campaign: Campaign, actor, owner=..., assignees=None) -> Campaign:  # noqa: ANN001
    """Set who is accountable and who is working on it.

    `owner` defaults to a sentinel rather than None so that clearing the
    owner and leaving it alone are different instructions.
    """
    if not policies.area_available(actor, campaign.service_type):
        raise PermissionDenied("This service workspace is disabled.")
    if not policies.can_assign_campaigns(actor, campaign.organization):
        raise PermissionDenied("You may not assign campaigns.")

    changes = []

    if owner is not ... and owner != campaign.owner:
        campaign.owner = owner
        campaign.save(update_fields=["owner", "updated_at"])
        changes.append(
            f"owner set to {owner.get_full_name() or owner.email}"
            if owner else "owner removed"
        )

    if assignees is not None:
        before = set(campaign.assignees.values_list("pk", flat=True))
        campaign.assignees.set(assignees)
        after = {user.pk for user in assignees}
        if before != after:
            changes.append(f"{len(after)} person/people working on it")

    if changes:
        _record(campaign, kind=CampaignEventKind.ASSIGNMENT, actor=actor,
                body="; ".join(changes).capitalize() + ".", is_internal=True)

    return campaign


@transaction.atomic
def add_note(*, campaign: Campaign, body: str, actor,  # noqa: ANN001
             is_internal: bool = True) -> CampaignEvent:
    """Add a note to a campaign's history.

    Internal by default; the caller opts out. The safe mistake is a note
    the client does not see.
    """
    if not policies.area_available(actor, campaign.service_type):
        raise PermissionDenied("This service workspace is disabled.")
    if not policies.can_edit_campaigns(actor, campaign.organization):
        raise PermissionDenied("You may not write on this campaign.")

    body = (body or "").strip()
    if not body:
        raise ValidationError("A note needs something in it.")

    return _record(campaign, kind=CampaignEventKind.NOTE, actor=actor,
                   body=body, is_internal=is_internal)


# ---------------------------------------------------------------------------
# Telling the client
# ---------------------------------------------------------------------------


def _notify_client(campaign: Campaign) -> None:
    """Tell the client's own people, in-app.

    Addressed to the members of that organization and nobody else — a
    notification is a read like any other, and the isolation rule applies
    to it just the same.
    """
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify
    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    if campaign.status not in CLIENT_VISIBLE_STATUSES:
        return

    members = (
        OrganizationMember.objects
        .filter(organization_id=campaign.organization_id,
                status__in=ACTIVE_MEMBERSHIP_STATUSES)
        .select_related("user")
    )

    title = (f"{campaign.name} is live" if campaign.is_running
             else f"{campaign.name}: {campaign.get_status_display().lower()}")

    for member in members:
        notify(
            recipient=member.user, title=title,
            body=campaign.client_summary[:300],
            url="/organization/area/campaigns/",
            level=NotificationLevel.INFO, category="campaign",
        )
