"""Private conversations between one client and their assigned agency team."""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.organizations.models import OrganizationOwnedModel


class Conversation(OrganizationOwnedModel, TimeStampedModel):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="client_conversations"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "client"], name="one_conversation_per_client_org"
            )
        ]


class Message(TimeStampedModel):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.PROTECT, related_name="messages"
    )
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    quote = models.ForeignKey("leads.QuoteRequest", on_delete=models.PROTECT, null=True, blank=True,
                              related_name="conversation_messages")
    subscription = models.ForeignKey("subscriptions.ClientSubscription", on_delete=models.PROTECT,
                                     null=True, blank=True, related_name="conversation_messages")
    body = models.TextField(max_length=5000)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
