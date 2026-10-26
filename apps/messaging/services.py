"""Persist chat before notifying its participants. No email or SMS transport."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.messaging.models import Conversation, Message
from apps.messaging.policies import may_access
from apps.notifications.services import notify


@transaction.atomic
def send(*, actor, organization, client, body, quote=None, subscription=None):
    if not may_access(actor, organization, client, "messaging_create"):
        raise PermissionDenied
    from apps.messaging.references import validate

    validate(
        actor=actor,
        organization=organization,
        client=client,
        quote=quote,
        subscription=subscription,
    )
    body = body.strip()
    if not body or len(body) > 5000:
        raise ValidationError("Write a message of 1–5,000 characters.")
    conversation, _ = Conversation.objects.get_or_create(organization=organization, client=client)
    message = Message.objects.create(
        conversation=conversation, sender=actor, body=body, quote=quote, subscription=subscription
    )
    if actor.is_staff_member:
        notify(
            recipient=client,
            title="A new message from your account team",
            url=reverse("organizations:client_desk"),
            category="messaging",
        )
    else:
        for staff in get_user_model().objects.filter(status="active").exclude(user_type="client"):
            if may_access(staff, organization, client):
                notify(
                    recipient=staff,
                    title=f"New message from {client.get_full_name()}",
                    url=reverse("staff:client_desk", args=[organization.slug, client.pk]),
                    category="messaging",
                )
    return message


def mark_read(*, actor, conversation):
    if not may_access(actor, conversation.organization, conversation.client):
        raise PermissionDenied
    from apps.notifications.services import mark_related_read

    read_at = timezone.now()
    messages = conversation.messages.filter(read_at__isnull=True, created_at__lte=read_at)
    if actor.is_staff_member:
        messages = messages.filter(sender=conversation.client)
    else:
        messages = messages.exclude(sender=actor)
    messages.update(read_at=read_at)
    url = (reverse("staff:client_desk", args=[conversation.organization.slug,
                                            conversation.client_id])
           if actor.is_staff_member else reverse("organizations:client_desk"))
    mark_related_read(user=actor, category="messaging", url=url, through=read_at)
