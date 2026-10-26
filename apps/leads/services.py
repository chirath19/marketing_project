"""Write operations for leads and the Inbox.

`record_submission` is the one that matters: it is the single path every
public form takes, so what happens on submission — store, attach to a
lead, log the activity, notify staff — happens once and the same way for
every form.

Nothing in here sends anything outbound.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.events import DomainEvent, bus
from apps.leads import policies
from apps.leads.models import (
    ActivityKind,
    ContactSubmission,
    Lead,
    LeadActivity,
    LeadSource,
    LeadStatus,
    QuoteItem,
    SubmissionKind,
)

logger = logging.getLogger(__name__)


#: Status transitions the pipeline allows. Declared as data so an
#: unexpected move raises rather than quietly rewriting history.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    LeadStatus.NEW: frozenset({LeadStatus.CONTACTED, LeadStatus.QUALIFIED,
                               LeadStatus.LOST, LeadStatus.ARCHIVED}),
    LeadStatus.CONTACTED: frozenset({LeadStatus.QUALIFIED, LeadStatus.PROPOSAL,
                                     LeadStatus.LOST, LeadStatus.ARCHIVED}),
    LeadStatus.QUALIFIED: frozenset({LeadStatus.PROPOSAL, LeadStatus.WON,
                                     LeadStatus.LOST, LeadStatus.ARCHIVED}),
    LeadStatus.PROPOSAL: frozenset({LeadStatus.WON, LeadStatus.LOST,
                                    LeadStatus.ARCHIVED}),
    LeadStatus.WON: frozenset({LeadStatus.ARCHIVED}),
    LeadStatus.LOST: frozenset({LeadStatus.CONTACTED, LeadStatus.ARCHIVED}),
    LeadStatus.ARCHIVED: frozenset({LeadStatus.NEW, LeadStatus.CONTACTED}),
}


def _touch(lead: Lead) -> None:
    lead.last_activity_at = timezone.now()
    lead.save(update_fields=["last_activity_at", "updated_at"])


@transaction.atomic
def record_submission(*, name: str, email: str, message: str,
                      kind: str = SubmissionKind.CONTACT,
                      source: str = LeadSource.CONTACT_FORM,
                      company: str = "", phone: str = "", website: str = "",
                      subject: str = "", page_url: str = "",
                      objective: str = "", budget_range: str = "",
                      submitted_by=None, organization=None,
                      ip_hash: str = "", user_agent: str = "",
                      is_spam: bool = False, spam_reason: str = "",
                      quote_items: list[dict] | None = None) -> ContactSubmission:
    """Store a public submission and raise it with staff.

    The one path every form takes. A submission flagged as spam is still
    stored and still attached to nothing — it does not create a lead or a
    notification, so it cannot pollute the pipeline, but it is there to
    be rescued.
    """
    normalised_email = (email or "").strip().lower()

    submission = ContactSubmission.objects.create(
        kind=kind, name=name.strip()[:150], company=company.strip()[:200],
        email=normalised_email, phone=phone.strip()[:32],
        website=website.strip()[:300], subject=subject.strip()[:200],
        message=message.strip(), source=source, page_url=page_url[:500],
        objective=objective.strip()[:120], budget_range=budget_range.strip()[:60],
        ip_hash=ip_hash, user_agent=user_agent[:300],
        is_spam=is_spam, spam_reason=spam_reason[:120],
    )

    for index, item in enumerate(quote_items or [], start=1):
        QuoteItem.objects.create(
            submission=submission,
            service=item.get("service"),
            package=item.get("package"),
            name=item["name"][:250],
            price_display=item.get("price_display", "")[:40],
            billing_display=item.get("billing_display", "")[:40],
            order=index * 10,
        )

    if is_spam:
        logger.info("Submission flagged as spam (%s) from %s",
                    spam_reason, normalised_email)
        return submission

    lead = _attach_to_lead(submission)
    if organization is not None and lead.organization_id is None:
        lead.organization = organization
        lead.save(update_fields=["organization", "updated_at"])
    submission.lead = lead
    submission.save(update_fields=["lead", "updated_at"])

    bus.publish(DomainEvent("lead.submission_received", {
        "submission_id": submission.pk,
        "lead_id": lead.pk,
        "kind": kind,
        "email": normalised_email,
    }))

    if kind == SubmissionKind.QUOTE_REQUEST:
        # The one path a quote request takes. Created here rather than in
        # the view so that every quote — public form today, staff-entered
        # or API tomorrow — goes through the same door and ends up with
        # the same timeline, reference and notification.
        from apps.leads import quote_services

        quote_services.create_from_submission(
            submission=submission, lead=lead,
            submitted_by=submitted_by, organization=organization,
        )
    else:
        _notify_staff(submission, lead)

    logger.info("Submission stored: %s (%s)", normalised_email, kind)
    return submission


def _attach_to_lead(submission: ContactSubmission) -> Lead:
    """Find the lead this submission belongs to, or start one.

    Matched on email, so a second enquiry from the same person joins the
    existing record instead of creating a duplicate somebody has to merge
    later. A lead that was closed is reopened rather than left looking
    settled while new mail arrives.
    """
    lead = Lead.objects.filter(email=submission.email).order_by("-pk").first()

    if lead is None:
        lead = Lead.objects.create(
            name=submission.name, company=submission.company,
            email=submission.email, phone=submission.phone,
            website=submission.website, source=submission.source,
            status=LeadStatus.NEW,
        )
        LeadActivity.objects.create(
            lead=lead, kind=ActivityKind.SUBMISSION,
            body=f"{submission.get_kind_display()} received.",
        )
        return lead

    if lead.status in {LeadStatus.LOST, LeadStatus.ARCHIVED}:
        previous = lead.status
        lead.status = LeadStatus.CONTACTED
        lead.closed_at = None
        lead.save(update_fields=["status", "closed_at", "updated_at"])
        LeadActivity.objects.create(
            lead=lead, kind=ActivityKind.STATUS,
            body=f"Reopened by a new enquiry (was {previous}).",
        )

    # Fill in anything the first enquiry did not carry.
    changed = []
    for field in ("company", "phone", "website"):
        if not getattr(lead, field) and getattr(submission, field):
            setattr(lead, field, getattr(submission, field))
            changed.append(field)
    if changed:
        lead.save(update_fields=[*changed, "updated_at"])

    LeadActivity.objects.create(
        lead=lead, kind=ActivityKind.SUBMISSION,
        body=f"Another {submission.get_kind_display().lower()} received.",
    )
    _touch(lead)
    return lead


def _notify_staff(submission: ContactSubmission, lead: Lead) -> None:
    """Raise the submission with whoever can act on it.

    In-app only. There is no email here and there is not meant to be —
    the Inbox is the delivery mechanism.
    """
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify_permission_holders

    permission = ("permissions.quotes_view"
                  if submission.kind == SubmissionKind.QUOTE_REQUEST
                  else "permissions.leads_view")

    notify_permission_holders(
        permission=permission,
        title=f"New {submission.get_kind_display().lower()} from {submission.name}",
        body=submission.preview,
        url=submission.get_absolute_url(),
        level=NotificationLevel.ACTION,
        category="lead",
    )


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


@transaction.atomic
def mark_read(*, submission: ContactSubmission, actor) -> ContactSubmission:  # noqa: ANN001
    if not policies.can_view_leads(actor):
        raise PermissionDenied("You may not read enquiries.")

    if submission.read_at is None:
        submission.read_at = timezone.now()
        submission.read_by = actor if getattr(actor, "pk", None) else None
        submission.save(update_fields=["read_at", "read_by", "updated_at"])
    from apps.notifications.services import mark_related_read

    mark_related_read(user=actor, category="lead", url=submission.get_absolute_url())
    return submission


@transaction.atomic
def mark_unread(*, submission: ContactSubmission, actor) -> ContactSubmission:  # noqa: ANN001
    if not policies.can_view_leads(actor):
        raise PermissionDenied("You may not change enquiries.")

    submission.read_at = None
    submission.read_by = None
    submission.save(update_fields=["read_at", "read_by", "updated_at"])
    return submission


@transaction.atomic
def set_archived(*, submission: ContactSubmission, actor,  # noqa: ANN001
                 archived: bool) -> ContactSubmission:
    """Take a submission out of the Inbox, or put it back.

    Archiving hides it from the working list and keeps the row — it is
    still the record of what was sent.
    """
    if not policies.can_edit_leads(actor):
        raise PermissionDenied("You may not archive enquiries.")

    submission.is_archived = archived
    submission.save(update_fields=["is_archived", "updated_at"])
    return submission


@transaction.atomic
def set_spam(*, submission: ContactSubmission, actor, is_spam: bool,  # noqa: ANN001
             reason: str = "") -> ContactSubmission:
    """Flag a submission as spam, or rescue one that was flagged wrongly.

    Rescuing creates the lead the submission never got, so a false
    positive can be recovered rather than merely un-hidden.
    """
    if not policies.can_edit_leads(actor):
        raise PermissionDenied("You may not change enquiries.")

    submission.is_spam = is_spam
    submission.spam_reason = (reason or
                              ("Marked by staff" if is_spam else ""))[:120]

    if not is_spam and submission.lead_id is None:
        lead = _attach_to_lead(submission)
        submission.lead = lead

    submission.save(update_fields=["is_spam", "spam_reason", "lead", "updated_at"])
    return submission


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


@transaction.atomic
def change_status(*, lead: Lead, new_status: str, actor, note: str = "") -> Lead:
    if new_status not in LeadStatus.values:
        raise ValidationError(f"{new_status!r} is not a valid lead status.")

    if not policies.can_edit_leads(actor):
        raise PermissionDenied("You may not change leads.")

    current = lead.status
    if current == new_status:
        return lead

    if new_status not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValidationError(
            f"A lead cannot move from {current} to {new_status}."
        )

    lead.status = new_status
    lead.closed_at = (timezone.now()
                      if new_status in {LeadStatus.WON, LeadStatus.LOST}
                      else None)
    lead.last_activity_at = timezone.now()
    lead.save(update_fields=["status", "closed_at", "last_activity_at",
                             "updated_at"])

    LeadActivity.objects.create(
        lead=lead, kind=ActivityKind.STATUS, actor=actor,
        body=note or f"Moved from {current} to {new_status}.",
    )

    bus.publish(DomainEvent("lead.status_changed", {
        "lead_id": lead.pk, "from_status": current, "to_status": new_status,
        "actor_id": getattr(actor, "pk", None),
    }))
    return lead


@transaction.atomic
def assign(*, lead: Lead, assignee, actor) -> Lead:  # noqa: ANN001
    """Give a lead an owner, or take it away.

    The new owner is notified in-app. An unassigned lead is one nobody is
    looking at, which is what the dashboard metric is for.
    """
    if not policies.can_assign_leads(actor):
        raise PermissionDenied("You may not assign leads.")

    if assignee is not None and not assignee.is_staff_member:
        raise ValidationError("Leads are assigned to staff.")

    previous = lead.assigned_to
    lead.assigned_to = assignee
    lead.last_activity_at = timezone.now()
    lead.save(update_fields=["assigned_to", "last_activity_at", "updated_at"])

    LeadActivity.objects.create(
        lead=lead, kind=ActivityKind.ASSIGNMENT, actor=actor,
        body=(f"Assigned to {assignee.get_full_name()}." if assignee
              else f"Unassigned (was {previous.get_full_name()})."
              if previous else "Unassigned."),
    )

    if assignee is not None and assignee != actor:
        from apps.notifications.models import NotificationLevel
        from apps.notifications.services import notify

        notify(
            recipient=assignee,
            title=f"{lead.name} was assigned to you",
            body=lead.company or lead.email,
            url=lead.get_absolute_url(),
            level=NotificationLevel.ACTION,
            category="lead",
        )

    return lead


@transaction.atomic
def add_note(*, lead: Lead, actor, body: str) -> LeadActivity:
    """Add an internal note.

    Staff only, in both directions: a client never sees these and never
    writes one.
    """
    if not policies.can_edit_leads(actor):
        raise PermissionDenied("You may not add notes.")

    cleaned = (body or "").strip()
    if not cleaned:
        raise ValidationError("A note needs something in it.")

    activity = LeadActivity.objects.create(
        lead=lead, kind=ActivityKind.NOTE, actor=actor, body=cleaned,
        is_internal=True,
    )
    _touch(lead)
    return activity
