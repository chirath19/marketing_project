"""Write operations for the Subscriptions domain.

The only place a client's services change. Every function authorises
through `policies.py` first — so the rule holds whether the caller is a
staff view, an accepted quote, a management command or something not
written yet.

Nothing here sends anything outbound. Activating a service raises an
in-app notification for the client's own people; that is the whole
delivery mechanism, as everywhere else in this version.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.events import DomainEvent, bus
from apps.subscriptions import policies
from apps.subscriptions.models import (
    ClientSubscription,
    SubscriptionEvent,
    SubscriptionEventKind,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)


#: Moves the lifecycle allows, declared as data so an unexpected one
#: raises rather than quietly rewriting what a client is paying for.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    SubscriptionStatus.PENDING: frozenset({
        SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED,
    }),
    SubscriptionStatus.ACTIVE: frozenset({
        SubscriptionStatus.PAUSED, SubscriptionStatus.COMPLETED,
        SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED,
    }),
    SubscriptionStatus.PAUSED: frozenset({
        SubscriptionStatus.ACTIVE, SubscriptionStatus.COMPLETED,
        SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED,
    }),
    # Finished work can be picked back up — clients renew, and a renewal
    # re-keyed as a new row loses the history of the first engagement.
    SubscriptionStatus.COMPLETED: frozenset({SubscriptionStatus.ACTIVE}),
    SubscriptionStatus.EXPIRED: frozenset({
        SubscriptionStatus.ACTIVE, SubscriptionStatus.COMPLETED,
    }),
    # Cancelled is the one dead end. It means the relationship ended
    # badly or never started; reviving it should be a deliberate new
    # agreement, not a dropdown.
    SubscriptionStatus.CANCELLED: frozenset(),
}

#: Status changes worth telling the client about. Pausing and resuming
#: affect what they see in their workspace, so they hear about those;
#: internal bookkeeping is not news.
CLIENT_VISIBLE_STATUSES = frozenset({
    SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED,
    SubscriptionStatus.COMPLETED, SubscriptionStatus.CANCELLED,
    SubscriptionStatus.EXPIRED,
})


def _record(subscription: ClientSubscription, *, kind: str, body: str,
            actor=None, is_internal: bool = True) -> SubscriptionEvent:  # noqa: ANN001
    return SubscriptionEvent.objects.create(
        subscription=subscription, kind=kind, body=body,
        actor=actor if getattr(actor, "pk", None) else None,
        is_internal=is_internal,
    )


@transaction.atomic
def create_subscription(*, organization, service, actor,  # noqa: ANN001
                        package=None, status: str = SubscriptionStatus.PENDING,
                        price=None, currency: str = "", billing_type: str = "",
                        custom_scope: str = "", starts_on=None, ends_on=None,
                        internal_notes: str = "", client_notes: str = "",
                        quote=None, name: str = "",
                        authorised: bool = False) -> ClientSubscription:
    """Attach a service to a client.

    Price and billing default to whatever the catalogue says **right
    now**, and are then copied onto the row. A later catalogue change
    must not silently alter what an existing client is paying.

    `authorised` is for `activate_accepted_quote` only: there the client's
    own acceptance is the authority, and it was checked by the caller.
    """
    if not authorised and not policies.can_create_subscriptions(actor, organization):
        raise PermissionDenied("You may not add services for this client.")

    if status not in SubscriptionStatus.values:
        raise ValidationError(f"{status!r} is not a subscription status.")

    priced = package or service

    subscription = ClientSubscription(
        organization=organization, service=service, package=package,
        name=name or (f"{service.name} — {package.name}" if package
                      else service.name),
        price=price if price is not None else getattr(priced, "price", None),
        currency=currency or getattr(priced, "currency", "") or "USD",
        billing_type=billing_type or getattr(priced, "billing_type", "") or "",
        custom_scope=custom_scope.strip(),
        starts_on=starts_on, ends_on=ends_on,
        internal_notes=internal_notes.strip(),
        client_notes=client_notes.strip(),
        status=status, quote=quote,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    # Validated rather than trusted: the uniqueness rule and the date
    # ordering are model-level invariants, and a service function is one
    # of the callers they exist to protect against.
    #
    # Nothing is excluded, and `organization` least of all: the "one open
    # subscription per service" constraint is partial and references it,
    # so excluding that field would skip the very check this call is here
    # to make — and the caller would meet a raw IntegrityError instead of
    # a sentence.
    subscription.full_clean()
    subscription.save()

    if status == SubscriptionStatus.ACTIVE:
        subscription.activated_at = timezone.now()
        subscription.save(update_fields=["activated_at", "updated_at"])

    _record(subscription, kind=SubscriptionEventKind.CREATED, actor=actor,
            body=f"{subscription.name} added for {organization.label}.",
            is_internal=False)

    bus.publish(DomainEvent("subscription.created", {
        "subscription_id": subscription.pk,
        "organization_id": organization.pk,
        "service_id": service.pk,
        "status": status,
    }))

    if status == SubscriptionStatus.ACTIVE:
        _notify_client(subscription, activated=True)

    logger.info("Subscription %s created for %s (%s)",
                subscription.pk, organization.slug, status)
    return subscription


@transaction.atomic
def change_status(*, subscription: ClientSubscription, status: str, actor,  # noqa: ANN001
                  note: str = "") -> ClientSubscription:
    """Move a service through its lifecycle.

    This is what makes a workspace module appear or disappear, so it is
    guarded by its own right rather than by general editing.
    """
    if not policies.can_change_status(actor, subscription.organization):
        raise PermissionDenied("You may not change this service's status.")

    if status not in SubscriptionStatus.values:
        raise ValidationError(f"{status!r} is not a subscription status.")

    if status == subscription.status:
        return subscription

    if status not in ALLOWED_TRANSITIONS.get(subscription.status, frozenset()):
        raise ValidationError(
            f"A {subscription.get_status_display().lower()} service cannot "
            f"become {SubscriptionStatus(status).label.lower()}."
        )

    previous = subscription.get_status_display()
    subscription.status = status
    fields = ["status", "updated_at"]

    if status == SubscriptionStatus.ACTIVE:
        if subscription.activated_at is None:
            subscription.activated_at = timezone.now()
            fields.append("activated_at")
        if subscription.starts_on is None:
            subscription.starts_on = timezone.localdate()
            fields.append("starts_on")
        # Reopening clears the end stamp; the row is live again and a
        # lingering "ended" date would contradict the status beside it.
        if subscription.ended_at is not None:
            subscription.ended_at = None
            fields.append("ended_at")
    elif status in {SubscriptionStatus.COMPLETED, SubscriptionStatus.CANCELLED,
                    SubscriptionStatus.EXPIRED}:
        subscription.ended_at = timezone.now()
        fields.append("ended_at")

    subscription.save(update_fields=fields)

    _record(subscription, kind=SubscriptionEventKind.STATUS, actor=actor,
            body=f"{previous} → {subscription.get_status_display()}"
                 + (f". {note}" if note else ""),
            is_internal=status not in CLIENT_VISIBLE_STATUSES)

    bus.publish(DomainEvent("subscription.status_changed", {
        "subscription_id": subscription.pk,
        "organization_id": subscription.organization_id,
        "status": status,
    }))

    _notify_client(subscription, activated=status == SubscriptionStatus.ACTIVE)
    return subscription


@transaction.atomic
def update_subscription(*, subscription: ClientSubscription, actor,  # noqa: ANN001
                        **fields) -> ClientSubscription:
    """Correct the commercial detail of a service already in place."""
    if not policies.can_edit_subscriptions(actor, subscription.organization):
        raise PermissionDenied("You may not change this service.")

    editable = {
        "name", "price", "currency", "billing_type", "custom_scope",
        "starts_on", "ends_on", "internal_notes", "client_notes", "package",
    }
    changed = []
    for field, value in fields.items():
        if field not in editable:
            continue
        if getattr(subscription, field) != value:
            setattr(subscription, field, value)
            changed.append(field)

    if not changed:
        return subscription

    subscription.full_clean()
    subscription.save(update_fields=[*changed, "updated_at"])

    # Named rather than listed as a diff: a history entry that says
    # "price changed" is readable a year later, one that says
    # "price: 2400 → 2800" is better, and one that dumps every field is
    # neither.
    labels = {
        "price": "price", "billing_type": "billing", "custom_scope": "scope",
        "starts_on": "start date", "ends_on": "end date",
        "client_notes": "notes for the client",
        "internal_notes": "internal notes", "name": "name",
        "package": "package", "currency": "currency",
    }
    summary = ", ".join(labels.get(field, field) for field in changed)
    _record(subscription, kind=SubscriptionEventKind.SCOPE, actor=actor,
            body=f"Updated {summary}.",
            is_internal="client_notes" not in changed)

    return subscription


@transaction.atomic
def add_note(*, subscription: ClientSubscription, body: str, actor,  # noqa: ANN001
             is_internal: bool = True) -> SubscriptionEvent:
    """Add a note to a service's history.

    Internal by default; the caller opts out. The safe mistake is a note
    the client does not see.
    """
    if not policies.can_edit_subscriptions(actor, subscription.organization):
        raise PermissionDenied("You may not write on this service.")

    body = (body or "").strip()
    if not body:
        raise ValidationError("A note needs something in it.")

    return _record(subscription, kind=SubscriptionEventKind.NOTE, actor=actor,
                   body=body, is_internal=is_internal)


# ---------------------------------------------------------------------------
# From an accepted quote
# ---------------------------------------------------------------------------


@transaction.atomic
def create_from_quote(*, quote, actor, status: str = SubscriptionStatus.PENDING,  # noqa: ANN001, ANN201
                      authorised: bool = False):
    """Turn an accepted quote into the services it agreed to.

    This is the step that was missing: before it, a client accepted a
    quote and somebody had to re-key every line by hand, which is both
    tedious and the obvious place for the agreed scope and the delivered
    scope to drift apart.

    Only lines still in scope become services, and only lines that point
    at a real catalogue entry — a free-text line has nothing to deliver
    against. Anything skipped is said out loud rather than dropped
    silently.
    """
    from apps.leads.models import QuoteStatus

    if quote.organization_id is None:
        raise ValidationError(
            "Attach this quote to a client organization before turning it "
            "into services."
        )

    if quote.status != QuoteStatus.ACCEPTED:
        raise ValidationError("Only an accepted quote becomes a service.")

    if not authorised and not policies.can_create_subscriptions(actor, quote.organization):
        raise PermissionDenied("You may not add services for this client.")

    created, skipped = [], []

    for item in quote.items.all():
        if not item.is_included:
            continue
        if item.service_id is None:
            skipped.append(f"{item.name} (not a catalogue service)")
            continue

        existing = ClientSubscription.objects.filter(
            organization=quote.organization, service=item.service,
            status__in=["pending", "active", "paused"],
        ).first()
        if existing is not None:
            skipped.append(f"{item.name} (already on their account)")
            continue

        created.append(create_subscription(
            organization=quote.organization, service=item.service,
            package=item.package, actor=actor, status=status,
            price=item.quoted_amount,
            currency=item.currency, billing_type=item.billing_type,
            custom_scope=item.note, quote=quote,
            name=item.name, authorised=authorised,
        ))

    return created, skipped


def activate_accepted_quote(*, quote, actor=None):  # noqa: ANN001, ANN201
    """Put an accepted quote's services live, as part of the acceptance.

    Called by every path that records an acceptance — the client, staff,
    or a guest link — so an accepted quote is visibly active work rather
    than waiting for somebody to remember the next step. Never raises:
    the acceptance stands even if activation cannot happen, and the reason
    is written to the quote's internal timeline for staff to act on.

    Skipped for quotes behind a service change request, which
    `changes.apply` turns into services itself.
    """
    from apps.leads.models import QuoteActivity, QuoteActivityKind, QuoteStatus
    from apps.organizations import selectors as organizations
    from apps.subscriptions.models import ServiceChangeRequest

    if quote.status != QuoteStatus.ACCEPTED or quote.subscriptions.exists():
        return [], []
    if ServiceChangeRequest.objects.filter(quote=quote).exists():
        return [], []

    staff_actor = actor if getattr(actor, "is_staff_member", False) else None

    if quote.organization_id is None and quote.submitted_by_id:
        organization = organizations.primary_organization_for(quote.submitted_by)
        if organization and organizations.membership_for(quote.submitted_by, organization):
            quote.organization = organization
            quote.save(update_fields=["organization", "updated_at"])
    if quote.organization_id is None:
        QuoteActivity.objects.create(
            quote=quote, kind=QuoteActivityKind.SCOPE, actor=staff_actor, is_internal=True,
            body="Accepted, but not attached to a client organization. Attach one and "
                 "its services are activated automatically.",
        )
        return [], []

    try:
        with transaction.atomic():
            created, skipped = create_from_quote(
                quote=quote, actor=staff_actor, status=SubscriptionStatus.ACTIVE,
                authorised=True,
            )
    except ValidationError as exc:
        logger.warning("Could not activate services for %s: %s", quote.reference, exc)
        created, skipped = [], exc.messages

    parts = []
    if created:
        parts.append("Activated: " + ", ".join(item.name for item in created) + ".")
    if skipped:
        parts.append("Not activated: " + "; ".join(skipped) + ".")
    if parts:
        QuoteActivity.objects.create(
            quote=quote, kind=QuoteActivityKind.SCOPE, actor=staff_actor,
            body=" ".join(parts), is_internal=True,
        )
    return created, skipped


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


@transaction.atomic
def expire_due(*, actor=None, on=None) -> list[ClientSubscription]:  # noqa: ANN001
    """Mark services whose agreed end date has passed.

    Expiry is a recorded status rather than a calculation done at read
    time, so the history says when it happened. Called from a management
    command — there is no scheduler in this version, which is a
    deliberate constraint, so somebody runs it.
    """
    due = list(ClientSubscription.objects.due_to_expire(on=on))

    for subscription in due:
        subscription.status = SubscriptionStatus.EXPIRED
        subscription.ended_at = timezone.now()
        subscription.save(update_fields=["status", "ended_at", "updated_at"])
        _record(subscription, kind=SubscriptionEventKind.STATUS, actor=actor,
                body=f"Expired: the agreed end date was "
                     f"{subscription.ends_on:%-d %B %Y}.",
                is_internal=False)
        bus.publish(DomainEvent("subscription.expired", {
            "subscription_id": subscription.pk,
            "organization_id": subscription.organization_id,
        }))

    if due:
        logger.info("Expired %s subscription(s)", len(due))
    return due


# ---------------------------------------------------------------------------
# Telling the client
# ---------------------------------------------------------------------------


def _notify_client(subscription: ClientSubscription, *, activated: bool) -> None:
    """Tell the client's own people, in-app.

    Addressed to the members of that organization and nobody else, which
    is the same isolation rule the rest of the domain runs on — a
    notification is a leak like any other read.
    """
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify
    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    if subscription.status not in CLIENT_VISIBLE_STATUSES:
        return

    members = (
        OrganizationMember.objects
        .filter(organization_id=subscription.organization_id,
                status__in=ACTIVE_MEMBERSHIP_STATUSES)
        .select_related("user")
    )

    title = (f"{subscription.name} is now active"
             if activated
             else f"{subscription.name}: {subscription.get_status_display().lower()}")

    for member in members:
        notify(
            recipient=member.user, title=title,
            body=subscription.client_notes[:300],
            url="/organization/services/",
            level=NotificationLevel.INFO, category="subscription",
        )
