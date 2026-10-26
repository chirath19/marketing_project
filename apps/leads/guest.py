"""Private guest quotation follow-up without an outbound notification provider."""

import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.leads.models import GuestQuoteAccess, QuoteActivity, QuoteActivityKind, QuoteStatus
from apps.notifications.services import notify_permission_holders


def issue(quote):
    token = secrets.token_urlsafe(32)
    GuestQuoteAccess.objects.create(
        quote=quote,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(days=90),
    )
    return token


def resolve(token, *, lock=False):
    rows = GuestQuoteAccess.objects.select_related("quote", "quote__organization")
    if lock:
        rows = rows.select_for_update(of=("self", "quote"))
    access = rows.filter(
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at__gt=timezone.now()
    ).first()
    if not access or access.quote.submitted_by_id:
        raise Http404("This private quotation link is unavailable.")
    return access.quote


@transaction.atomic
def respond(*, token, action, body=""):
    quote = resolve(token, lock=True)
    body = body.strip()
    if len(body) > 4000:
        raise ValidationError("Keep the message under 4,000 characters.")
    if action == "message":
        if not body:
            raise ValidationError("Write a message before sending.")
        kind = QuoteActivityKind.CLIENT_MESSAGE
    elif action in {"accept", "decline"}:
        if quote.status != QuoteStatus.PROPOSAL_READY:
            raise ValidationError("This quotation is not ready for a decision.")
        quote.status = QuoteStatus.ACCEPTED if action == "accept" else QuoteStatus.DECLINED
        quote.decided_at = timezone.now()
        kind = QuoteActivityKind.STATUS
        body = (
            "Accepted" if action == "accept" else "Declined"
        ) + " through the private guest link."
    else:
        raise ValidationError("Choose a valid response.")
    quote.last_activity_at = timezone.now()
    quote.save(update_fields=["status", "decided_at", "last_activity_at", "updated_at"])
    QuoteActivity.objects.create(quote=quote, kind=kind, body=body, is_internal=False)
    if quote.status == QuoteStatus.ACCEPTED and action == "accept":
        from apps.subscriptions.services import activate_accepted_quote

        activate_accepted_quote(quote=quote)
    notify_permission_holders(
        permission="permissions.quotes_view",
        organization=quote.organization,
        title=f"Guest response on {quote.reference}",
        body=body[:300],
        url=quote.get_absolute_url(),
        category="quote",
    )
    return quote


def require_guest_quote(view):
    from functools import wraps

    @wraps(view)
    def guarded(request, token):
        request.guest_quote = resolve(token)
        return view(request, token)
    return guarded
