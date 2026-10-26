"""One conversation per quote.

Talk about a quote used to live in two places: replies on the quote's own
timeline, and chat messages tagged with the quote in the client's private
conversation. Now a reply on a quote *is* a tagged chat message whenever
the quote belongs to a signed-in client of an active organization, so the
same words appear on the quote page and in the Conversation tab.

A quote without such a client (a guest request, or one only attached to an
organization) keeps its replies on the quote timeline, which is the only
place those readers can see.

Nothing here sends email: every notice is in-app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.leads import policies
from apps.leads.models import QuoteActivity, QuoteActivityKind, QuoteRequest, QuoteStatus
from apps.permissions.access import can

MAX_LENGTH = 5000

#: What the client is told when a quote reaches a status they can see.
CLIENT_STATUS_NOTICES = {
    QuoteStatus.CLARIFICATION_REQUIRED: "We need a few details for {ref}",
    QuoteStatus.PROPOSAL_READY: "Your proposal {ref} is ready for review",
    QuoteStatus.ACCEPTED: "{ref} is accepted and now active",
    QuoteStatus.DECLINED: "{ref} has been marked declined",
}


def thread_client(quote: QuoteRequest):
    """The client whose private conversation carries this quote, or None."""
    from apps.core.features import visible
    from apps.organizations.selectors import membership_for

    user = quote.submitted_by
    if user is None or quote.organization_id is None:
        return None
    if not user.is_client or not user.is_active or quote.organization.status != "active":
        return None
    if not membership_for(user, quote.organization) or not visible("messages", user):
        return None
    return user


def client_recipients(quote: QuoteRequest) -> list:
    """Clients who should hear about this quote: whoever sent it, otherwise
    everyone in the organization it belongs to."""
    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    if quote.submitted_by_id:
        user = quote.submitted_by
        return [user] if policies.can_client_see_quote(user, quote) else []
    if quote.organization_id is None:
        return []
    members = OrganizationMember.objects.filter(
        organization_id=quote.organization_id,
        status__in=ACTIVE_MEMBERSHIP_STATUSES,
        user__status="active",
        user__user_type="client",
    ).select_related("user")
    return [member.user for member in members]


def notify_client(quote: QuoteRequest, *, title: str, body: str = "", action: bool = False) -> None:
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify

    for recipient in client_recipients(quote):
        notify(
            recipient=recipient, title=title, body=body[:300], url=quote.get_client_url(),
            level=NotificationLevel.ACTION if action else NotificationLevel.INFO,
            category="quote",
        )


def notify_status(quote: QuoteRequest, note: str = "") -> None:
    template = CLIENT_STATUS_NOTICES.get(quote.status)
    if template:
        notify_client(
            quote, title=template.format(ref=quote.reference), body=note,
            action=quote.status in {QuoteStatus.CLARIFICATION_REQUIRED,
                                    QuoteStatus.PROPOSAL_READY},
        )


def _notify_staff(quote: QuoteRequest, *, actor, body: str) -> None:
    """The owner hears about a client reply directly; everyone else only if
    there is no owner."""
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify, notify_permission_holders

    title = f"{quote.contact_name} replied on {quote.reference}"
    if quote.assigned_to_id and can(quote.assigned_to, "quotes_view", quote):
        notify(recipient=quote.assigned_to, title=title, body=body[:300],
               url=quote.get_absolute_url(), level=NotificationLevel.ACTION, category="quote")
    else:
        notify_permission_holders(
            permission="permissions.quotes_view", title=title, body=body[:300],
            url=quote.get_absolute_url(), level=NotificationLevel.ACTION,
            category="quote", exclude=actor, organization=quote.organization,
        )


@transaction.atomic
def reply(*, quote: QuoteRequest, actor, body: str):  # noqa: ANN001, ANN201
    """Post a client-visible message on a quote, from staff or the client."""
    from apps.messaging.models import Conversation, Message

    staff = actor.is_staff_member
    if staff and not can(actor, "quotes_edit", quote):
        raise PermissionDenied("You may not write on this quote.")
    if not staff and not policies.can_client_see_quote(actor, quote):
        raise PermissionDenied("That quote is not yours.")

    body = (body or "").strip()
    if not body or len(body) > MAX_LENGTH:
        raise ValidationError("Write a message of 1–5,000 characters.")

    client = thread_client(quote)
    if client and (staff or actor.pk == client.pk):
        conversation, _ = Conversation.objects.get_or_create(
            organization=quote.organization, client=client
        )
        entry = Message.objects.create(
            conversation=conversation, sender=actor, body=body, quote=quote
        )
    else:
        entry = QuoteActivity.objects.create(
            quote=quote, actor=actor, body=body, is_internal=False,
            kind=QuoteActivityKind.NOTE if staff else QuoteActivityKind.CLIENT_MESSAGE,
        )

    QuoteRequest.objects.filter(pk=quote.pk).update(
        last_activity_at=timezone.now(), updated_at=timezone.now()
    )
    if staff:
        notify_client(quote, title=f"New reply on {quote.reference}", body=body, action=True)
    else:
        _notify_staff(quote, actor=actor, body=body)
    return entry


def mark_read(*, quote: QuoteRequest, actor) -> None:
    """Opening a quote reads the tagged chat messages addressed to this reader."""
    from apps.messaging.models import Message

    rows = Message.objects.filter(quote=quote, read_at__isnull=True)
    if actor.is_staff_member:
        rows = rows.filter(sender=quote.submitted_by_id)
    else:
        rows = rows.filter(conversation__client=actor).exclude(sender=actor)
    rows.update(read_at=timezone.now())


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


@dataclass
class Entry:
    """One line of a quote thread, whatever it is stored as."""

    created_at: datetime
    body: str
    sender: object = None
    is_event: bool = False
    is_internal: bool = False
    read_at: datetime | None = None
    label: str = ""
    was_unread: bool = False
    outgoing: bool = False
    has_receipt: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def sender_id(self):  # noqa: ANN201
        return getattr(self.sender, "pk", None)


#: Timeline kinds that are things somebody said rather than things that happened.
SPOKEN = {QuoteActivityKind.NOTE, QuoteActivityKind.CLIENT_MESSAGE}


def entries(quote: QuoteRequest, viewer) -> list[Entry]:
    """The merged thread, oldest first, with internal entries for staff only."""
    from apps.leads.selectors import client_visible_activities
    from apps.messaging.models import Message
    from apps.messaging.presentation import group

    staff = viewer.is_staff_member
    activities = (
        list(quote.activities.select_related("actor")) if staff
        else client_visible_activities(quote)
    )
    rows = [
        Entry(
            created_at=activity.created_at, body=activity.body, sender=activity.actor,
            is_event=activity.kind not in SPOKEN, is_internal=activity.is_internal,
            label=activity.get_kind_display(),
        )
        for activity in activities
    ]

    messages = Message.objects.filter(quote=quote).select_related("sender")
    if not staff:
        messages = messages.filter(conversation__client=viewer,
                                   conversation__organization_id=quote.organization_id)
    for message in messages:
        incoming = (message.sender_id == quote.submitted_by_id if staff
                    else message.sender_id != viewer.pk)
        rows.append(Entry(
            created_at=message.created_at, body=message.body, sender=message.sender,
            read_at=message.read_at, was_unread=incoming and message.read_at is None,
            has_receipt=True,
        ))

    for row in rows:
        # The reader's side of the conversation: the whole team for staff.
        row.outgoing = row.sender is not None and (
            row.sender.is_staff_member if staff else row.sender_id == viewer.pk
        )
    rows.sort(key=lambda entry: entry.created_at)
    return group(rows)
