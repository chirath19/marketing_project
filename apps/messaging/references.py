"""Validate links without widening the recipient's access to a quotation or service."""

from django.core.exceptions import PermissionDenied, ValidationError

from apps.leads.policies import can_client_see_quote
from apps.permissions.access import can


def validate(*, actor, organization, client, subscription=None, quote=None):
    if subscription and subscription.organization_id != organization.pk:
        raise ValidationError("Choose a service in this client's organization.")
    if quote:
        if quote.organization_id != organization.pk or not can_client_see_quote(client, quote):
            raise ValidationError("Choose a quotation visible to this client.")
        if actor.is_staff_member and not can(actor, "quotes_view", quote):
            raise PermissionDenied
