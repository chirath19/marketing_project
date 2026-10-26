"""Write operations for quote requests.

Kept apart from `services.py` because a quote request has a lifecycle of
its own: its own status machine, its own owner, and — uniquely in this
domain — a client who can see it. Mixing that into the lead services
would have produced one module where every function needed a comment
explaining which of two workflows it belonged to.

Nothing here sends anything outbound. A new request raises an in-app
notification with the staff who hold `quotes_view`, appears in the Inbox
through its submission, and shows up in the client's own workspace when
they were signed in. That is the entire delivery mechanism, by design.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.events import DomainEvent, bus
from apps.leads import policies
from apps.leads.models import (
    ContactSubmission,
    Lead,
    QuoteActivity,
    QuoteActivityKind,
    QuoteRequest,
    QuoteRequestItem,
    QuoteStatus,
)
from apps.permissions.access import can

logger = logging.getLogger(__name__)


@transaction.atomic
def mark_viewed(*, quote, actor):
    """Acknowledge the reader's alerts without changing quotation status or scope."""
    from apps.notifications.services import mark_related_read
    from apps.permissions.access import can

    if actor.is_staff_member:
        if not can(actor, "quotes_view", quote):
            raise PermissionDenied
        url = quote.get_absolute_url()
        if quote.submission_id:
            ContactSubmission.objects.filter(pk=quote.submission_id, read_at__isnull=True).update(
                read_at=timezone.now(), read_by=actor
            )
            mark_related_read(user=actor, category="lead", url=quote.submission.get_absolute_url())
    else:
        if not policies.can_client_see_quote(actor, quote):
            raise PermissionDenied
        url = quote.get_client_url()
    mark_related_read(user=actor, category="quote", url=url)


#: Moves the workflow allows, declared as data.
#:
#: Written out rather than inferred so that an unexpected move raises
#: instead of quietly rewriting history, and so the shape of the process
#: is readable without tracing the views that drive it.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    QuoteStatus.NEW: frozenset({
        QuoteStatus.REVIEWING, QuoteStatus.CLARIFICATION_REQUIRED,
        QuoteStatus.DECLINED, QuoteStatus.CLOSED,
    }),
    QuoteStatus.REVIEWING: frozenset({
        QuoteStatus.CLARIFICATION_REQUIRED, QuoteStatus.PROPOSAL_READY,
        QuoteStatus.DECLINED, QuoteStatus.CLOSED,
    }),
    QuoteStatus.CLARIFICATION_REQUIRED: frozenset({
        QuoteStatus.REVIEWING, QuoteStatus.PROPOSAL_READY,
        QuoteStatus.DECLINED, QuoteStatus.CLOSED,
    }),
    QuoteStatus.PROPOSAL_READY: frozenset({
        QuoteStatus.ACCEPTED, QuoteStatus.DECLINED,
        QuoteStatus.CLARIFICATION_REQUIRED, QuoteStatus.CLOSED,
    }),
    # A won quote is finished. It can be filed away, not un-won: the
    # client agreed, and pretending otherwise loses the only record that
    # they did.
    QuoteStatus.ACCEPTED: frozenset({QuoteStatus.CLOSED}),
    # Both of these can be picked back up. People change their minds, and
    # a quote that cannot be reopened gets re-keyed as a duplicate.
    QuoteStatus.DECLINED: frozenset({QuoteStatus.REVIEWING, QuoteStatus.CLOSED}),
    QuoteStatus.CLOSED: frozenset({QuoteStatus.REVIEWING}),
}

#: Statuses the client is told about. A quote moving between internal
#: working states is not news to them; a proposal being ready is.
CLIENT_VISIBLE_STATUSES = frozenset({
    QuoteStatus.CLARIFICATION_REQUIRED, QuoteStatus.PROPOSAL_READY,
    QuoteStatus.ACCEPTED, QuoteStatus.DECLINED,
})


def _activate(quote: QuoteRequest, actor) -> None:  # noqa: ANN001
    """An accepted quote is live work: its services start straight away."""
    from apps.subscriptions.services import activate_accepted_quote

    activate_accepted_quote(quote=quote, actor=actor)


def _touch(quote: QuoteRequest) -> None:
    quote.last_activity_at = timezone.now()
    quote.save(update_fields=["last_activity_at", "updated_at"])


def _next_reference() -> str:
    """A human reference, unique and quotable out loud.

    Derived from the year and a per-year sequence rather than from the
    primary key, so the number a client reads back says roughly when the
    request was made. The count runs inside the caller's transaction and
    the column is unique, so two simultaneous requests cannot agree on a
    number without the second one failing and retrying.
    """
    year = timezone.now().year
    prefix = f"QR-{year}-"
    last = (
        QuoteRequest.objects.filter(reference__startswith=prefix)
        .order_by("-reference").values_list("reference", flat=True).first()
    )
    sequence = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{sequence:04d}"


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


@transaction.atomic
def create_from_submission(*, submission: ContactSubmission, lead: Lead | None,
                           submitted_by=None, organization=None,  # noqa: ANN001
                           objective: str = "",
                           budget_range: str = "") -> QuoteRequest:
    """Turn a stored quote submission into a workable request.

    Called from `record_submission`, so every public quote takes this
    path and nothing else creates one by hand.

    The contact details are **copied** onto the request rather than read
    through the lead. A quote has to say who it was for even after the
    lead's details are corrected, and a year later that difference is the
    entire reason for keeping the record.
    """
    quote = QuoteRequest.objects.create(
        reference=_next_reference(),
        submission=submission,
        lead=lead,
        organization=organization,
        submitted_by=submitted_by if getattr(submitted_by, "pk", None) else None,
        contact_name=submission.name,
        contact_email=submission.email,
        contact_phone=submission.phone,
        company_name=submission.company,
        website=submission.website,
        objective=objective or submission.objective,
        budget_range=budget_range or submission.budget_range,
        notes=submission.message,
        status=QuoteStatus.NEW,
    )

    for item in submission.quote_items.all():
        priced = item.package or item.service
        QuoteRequestItem.objects.create(
            quote=quote,
            service=item.service,
            package=item.package,
            name=item.name,
            price_display=item.price_display,
            billing_display=item.billing_display,
            quoted_amount=getattr(priced, "price", None),
            currency=getattr(priced, "currency", "") or "",
            billing_type=getattr(priced, "billing_type", "") or "",
            order=item.order,
        )

    QuoteActivity.objects.create(
        quote=quote, kind=QuoteActivityKind.SUBMITTED,
        body=f"Quote request received with {quote.items.count()} service"
             f"{'s' if quote.items.count() != 1 else ''}.",
        is_internal=False,
    )

    bus.publish(DomainEvent("quote.requested", {
        "quote_id": quote.pk,
        "reference": quote.reference,
        "organization_id": quote.organization_id,
        "email": quote.contact_email,
    }))

    _notify_staff(quote)
    logger.info("Quote request %s created for %s", quote.reference,
                quote.contact_email)
    return quote


def _notify_staff(quote: QuoteRequest) -> None:
    """Raise the request with whoever can price it.

    In-app only, and addressed by permission rather than to a list of
    people — so a notification can never reach somebody who would not be
    allowed to open what it points at.
    """
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify_permission_holders

    lines = ", ".join(item.name for item in quote.items.all()[:3]) or "no services"

    notify_permission_holders(
        permission="permissions.quotes_view",
        title=f"Quote request {quote.reference} from {quote.contact_name}",
        body=lines,
        url=quote.get_absolute_url(),
        level=NotificationLevel.ACTION,
        category="quote",
        exclude=quote.submitted_by, organization=quote.organization,
    )


# ---------------------------------------------------------------------------
# Working the request
# ---------------------------------------------------------------------------


@transaction.atomic
def change_status(*, quote: QuoteRequest, status: str, actor,  # noqa: ANN001
                  note: str = "") -> QuoteRequest:
    """Move a quote through the workflow.

    Accepting or declining needs its own right: adjusting scope is
    day-to-day work, recording that a client committed is not.
    """
    if status not in QuoteStatus.values:
        raise ValidationError(f"{status!r} is not a quote status.")

    decisive = status in {QuoteStatus.ACCEPTED, QuoteStatus.DECLINED}
    allowed = can(actor, "quotes_approve" if decisive else "quotes_edit", quote)
    if not allowed:
        raise PermissionDenied("You may not change this quote's status.")

    if status == quote.status:
        return quote

    if status not in ALLOWED_TRANSITIONS.get(quote.status, frozenset()):
        raise ValidationError(
            f"A quote cannot move from {quote.get_status_display()} to "
            f"{QuoteStatus(status).label}."
        )

    previous = quote.get_status_display()
    quote.status = status

    fields = ["status", "updated_at"]
    if decisive:
        quote.decided_at = timezone.now()
        fields.append("decided_at")
    if status == QuoteStatus.CLOSED:
        quote.closed_at = timezone.now()
        fields.append("closed_at")
    elif quote.closed_at is not None:
        quote.closed_at = None
        fields.append("closed_at")

    quote.save(update_fields=fields)

    QuoteActivity.objects.create(
        quote=quote, kind=QuoteActivityKind.STATUS, actor=actor,
        body=f"{previous} → {quote.get_status_display()}"
             + (f". {note}" if note else ""),
        # Internal churn stays internal; a change the client is waiting
        # on is one they should see without having to ask.
        is_internal=status not in CLIENT_VISIBLE_STATUSES,
    )

    bus.publish(DomainEvent("quote.status_changed", {
        "quote_id": quote.pk, "reference": quote.reference, "status": status,
    }))

    from apps.leads.quote_thread import notify_status

    notify_status(quote, note)
    if status == QuoteStatus.ACCEPTED:
        _activate(quote, actor)

    _touch(quote)
    return quote


@transaction.atomic
def assign(*, quote: QuoteRequest, assignee, actor) -> QuoteRequest:  # noqa: ANN001
    if not can(actor, "quotes_assign", quote):
        raise PermissionDenied("You may not assign quote requests.")

    quote.assigned_to = assignee
    quote.save(update_fields=["assigned_to", "updated_at"])

    QuoteActivity.objects.create(
        quote=quote, kind=QuoteActivityKind.ASSIGNMENT, actor=actor,
        body=(f"Assigned to {assignee.get_full_name() or assignee.email}."
              if assignee else "Owner removed."),
        is_internal=True,
    )
    _touch(quote)
    return quote


@transaction.atomic
def add_note(*, quote: QuoteRequest, body: str, actor,  # noqa: ANN001
             is_internal: bool = True) -> QuoteActivity:
    """Add a note to the timeline.

    `is_internal` defaults to True and the caller has to opt out, because
    the safe mistake is a note the client does not see.
    """
    if not can(actor, "quotes_edit", quote):
        raise PermissionDenied("You may not write on this quote.")

    body = (body or "").strip()
    if not body:
        raise ValidationError("A note needs something in it.")

    entry = QuoteActivity.objects.create(
        quote=quote, kind=QuoteActivityKind.NOTE, actor=actor,
        body=body, is_internal=is_internal,
    )
    if not is_internal:
        from apps.leads.quote_thread import notify_client

        notify_client(quote, title=f"New reply on {quote.reference}", body=body, action=True)
    _touch(quote)
    return entry


@transaction.atomic
def update_scope(*, quote: QuoteRequest, actor, summary: str | None = None,  # noqa: ANN001
                 lines: dict[int, dict] | None = None) -> QuoteRequest:
    """Adjust what is being quoted.

    The submission and its `QuoteItem` rows are untouched: they are the
    record of what was asked for. These rows are the agency's answer, and
    the difference between the two is often the useful part.
    """
    if not can(actor, "quotes_edit", quote):
        raise PermissionDenied("You may not change this quote's scope.")

    if quote.status in {QuoteStatus.ACCEPTED, QuoteStatus.CLOSED}:
        raise ValidationError("Agreed scope is locked. Create a new quotation for additional work.")

    changes: list[str] = []

    if summary is not None and summary.strip() != quote.staff_summary:
        quote.staff_summary = summary.strip()
        quote.save(update_fields=["staff_summary", "updated_at"])
        changes.append("scope summary updated")

    for item in quote.items.all():
        values = (lines or {}).get(item.pk)
        if not values:
            continue

        fields = []
        for field in ("quoted_amount", "note", "is_included"):
            if field in values and getattr(item, field) != values[field]:
                setattr(item, field, values[field])
                fields.append(field)

        if fields:
            if item.quoted_amount is not None and (
                not item.quoted_amount.is_finite() or item.quoted_amount < 0
            ):
                raise ValidationError("Quote amounts must be finite and non-negative.")
            item.full_clean()
            item.save(update_fields=[*fields, "updated_at"])
            if "is_included" in fields:
                changes.append(
                    f"{item.name} {'added to' if item.is_included else 'removed from'}"
                    " scope"
                )
            else:
                changes.append(f"{item.name} updated")

    if changes:
        # Not `.capitalize()`: it lowercases everything after the first
        # character, which turned "Technical SEO audit updated" into
        # "technical seo audit updated" and mangled every product name
        # that happened to land mid-sentence.
        summary_line = "; ".join(changes)
        QuoteActivity.objects.create(
            quote=quote, kind=QuoteActivityKind.SCOPE, actor=actor,
            body=summary_line[:1].upper() + summary_line[1:] + ".",
            is_internal=True,
        )
        _touch(quote)

    return quote


@transaction.atomic
def attach_to_organization(*, quote: QuoteRequest, organization, actor) -> QuoteRequest:  # noqa: ANN001
    """Point a quote at the client it belongs to.

    This is what makes it visible in that client's workspace, so it is
    guarded as an edit rather than left to whoever can view the list.
    """
    if not can(actor, "quotes_edit", quote):
        raise PermissionDenied("You may not change this quote.")

    if quote.organization_id == getattr(organization, "pk", None):
        return quote

    quote.organization = organization
    quote.save(update_fields=["organization", "updated_at"])

    QuoteActivity.objects.create(
        quote=quote, kind=QuoteActivityKind.NOTE, actor=actor,
        body=(f"Attached to {organization.label}. It is now visible in their "
              "workspace." if organization else "Detached from its client."),
        is_internal=True,
    )
    if organization and quote.status == QuoteStatus.ACCEPTED:
        _activate(quote, actor)
    _touch(quote)
    return quote


# ---------------------------------------------------------------------------
# What the client can do
# ---------------------------------------------------------------------------


def client_reply(*, quote: QuoteRequest, body: str, actor):  # noqa: ANN001, ANN201
    """A message from the client on their own quote.

    Stored in-app, in the quote's single conversation (see `quote_thread`),
    and the owner — or, with no owner, the quote team — is notified.
    """
    from apps.leads.quote_thread import reply

    return reply(quote=quote, actor=actor, body=body)


@transaction.atomic
def client_decision(*, quote: QuoteRequest, accepted: bool, actor,  # noqa: ANN001
                    note: str = "") -> QuoteRequest:
    """The client accepting or declining their own proposal.

    Only from `proposal_ready`: there is nothing to accept until there is
    something to accept, and a client who could accept a quote mid-draft
    would be agreeing to a figure the agency had not finished writing.
    """
    quote = QuoteRequest.objects.select_for_update().get(pk=quote.pk)
    if not policies.can_client_decide_quote(actor, quote):
        raise PermissionDenied("That quote is not yours.")

    if quote.status != QuoteStatus.PROPOSAL_READY:
        raise ValidationError("This quote is not ready for a decision yet.")

    quote.status = QuoteStatus.ACCEPTED if accepted else QuoteStatus.DECLINED
    quote.decided_at = timezone.now()
    quote.save(update_fields=["status", "decided_at", "updated_at"])

    QuoteActivity.objects.create(
        quote=quote, kind=QuoteActivityKind.STATUS, actor=actor,
        body=("Accepted by the client." if accepted else "Declined by the client.")
             + (f" {note}" if note else ""),
        is_internal=False,
    )

    bus.publish(DomainEvent("quote.decided", {
        "quote_id": quote.pk, "reference": quote.reference,
        "accepted": accepted,
    }))

    if accepted:
        _activate(quote, actor)

    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify, notify_permission_holders

    verb = "accepted" if accepted else "declined"
    title = f"{quote.contact_name} {verb} {quote.reference}"

    if quote.assigned_to_id and can(quote.assigned_to, "quotes_view", quote):
        notify(recipient=quote.assigned_to, title=title, body=note[:300],
               url=quote.get_absolute_url(),
               level=NotificationLevel.ACTION, category="quote")
    else:
        notify_permission_holders(
            permission="permissions.quotes_view", title=title, body=note[:300],
            url=quote.get_absolute_url(), level=NotificationLevel.ACTION,
            category="quote", exclude=actor, organization=quote.organization,
        )

    _touch(quote)
    return quote


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------


def totals_for(quote: QuoteRequest) -> dict:
    """What the quote currently adds up to.

    Monthly and one-off are kept apart, because adding them produces a
    number that means nothing. Lines quoted on scope are excluded and
    flagged, so a total is never presented as complete when it is not.
    """
    monthly = Decimal("0")
    one_time = Decimal("0")
    currency = ""
    has_custom = False

    for item in quote.included_items:
        if item.quoted_amount is None:
            has_custom = True
            continue
        currency = currency or item.currency
        if item.billing_type == "monthly":
            monthly += item.quoted_amount
        elif item.billing_type == "one_time":
            one_time += item.quoted_amount
        else:
            has_custom = True

    return {
        "monthly": monthly, "one_time": one_time,
        "currency": currency, "has_custom": has_custom,
    }


@transaction.atomic
def add_scope_line(*, actor, quote, **values):
    from apps.permissions.access import can
    quote = QuoteRequest.objects.select_for_update().get(pk=quote.pk)
    if not can(actor, 'quotes_edit', quote):
        raise PermissionDenied
    if quote.status in {QuoteStatus.ACCEPTED, QuoteStatus.CLOSED}:
        raise ValidationError('Agreed scope is locked. Create a new quotation for additional work.')
    values['currency'] = values['currency'].upper()
    item = QuoteRequestItem(quote=quote, order=quote.items.count() + 1, **values)
    item.full_clean()
    item.save()
    QuoteActivity.objects.create(quote=quote, actor=actor, kind=QuoteActivityKind.SCOPE,
                                 body=f'Added scope line: {item.name}', is_internal=True)
    return item
