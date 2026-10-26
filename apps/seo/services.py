"""Write operations for the SEO domain.

The only place SEO records change. Every function authorises through
`policies.py` first, so the rule holds whether the caller is a staff
view, the CSV importer or something written later.

Nothing here contacts a search engine, and nothing ever will through this
module. Positions, volumes and authority scores are entered by a person
or imported from a file they exported — a figure this platform did not
measure is one it must not present as its own.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.events import DomainEvent, bus
from apps.seo import policies
from apps.seo.models import (
    AuditStatus,
    Backlink,
    BacklinkStatus,
    IssueStatus,
    Keyword,
    KeywordRanking,
    SeoAudit,
    SeoTask,
    TaskStatus,
    TechnicalIssue,
)

logger = logging.getLogger(__name__)


def _require(actor, organization, *, action: str = "edit") -> None:  # noqa: ANN001
    checks = {
        "view": policies.can_view_seo,
        "create": policies.can_create_seo,
        "edit": policies.can_edit_seo,
        "deliver": policies.can_deliver_seo,
    }
    if not checks[action](actor, organization):
        raise PermissionDenied("You may not do that for this client.")


# ---------------------------------------------------------------------------
# Audits
# ---------------------------------------------------------------------------


@transaction.atomic
def create_audit(*, organization, title: str, actor, **fields) -> SeoAudit:  # noqa: ANN001
    _require(actor, organization, action="create")

    audit = SeoAudit(
        organization=organization, title=title.strip(),
        performed_by=actor if getattr(actor, "pk", None) else None,
        **fields,
    )
    audit.full_clean()
    audit.save()

    bus.publish(DomainEvent("seo.audit_created", {
        "audit_id": audit.pk, "organization_id": organization.pk,
    }))
    logger.info("SEO audit %s created for %s", audit.pk, organization.slug)
    return audit


@transaction.atomic
def update_audit(*, audit: SeoAudit, actor, **fields) -> SeoAudit:  # noqa: ANN001
    _require(actor, audit.organization)

    editable = {"title", "site_url", "performed_on", "summary",
                "internal_notes", "health_score", "pages_crawled",
                "score_source"}
    changed = [field for field, value in fields.items()
               if field in editable and getattr(audit, field) != value]
    for field in changed:
        setattr(audit, field, fields[field])

    if changed:
        audit.full_clean()
        audit.save(update_fields=[*changed, "updated_at"])
    return audit


@transaction.atomic
def deliver_audit(*, audit: SeoAudit, actor) -> SeoAudit:  # noqa: ANN001
    """Publish an audit to the client.

    Its own right, because everything in an audit is internal until
    somebody decides it is ready to be read — and a half-written finding
    read by the client causes exactly the conversation it was meant to
    prevent.
    """
    _require(actor, audit.organization, action="deliver")

    if not audit.summary.strip():
        raise ValidationError(
            "Write the summary first. It is the part the client reads."
        )

    audit.status = AuditStatus.DELIVERED
    audit.save(update_fields=["status", "updated_at"])

    _notify_client(
        audit.organization,
        title=f"Your SEO audit is ready: {audit.title}",
        body=audit.summary[:300],
    )

    bus.publish(DomainEvent("seo.audit_delivered", {
        "audit_id": audit.pk, "organization_id": audit.organization_id,
    }))
    return audit


@transaction.atomic
def add_issue(*, audit: SeoAudit, title: str, actor, **fields) -> TechnicalIssue:  # noqa: ANN001
    _require(actor, audit.organization)

    issue = TechnicalIssue(audit=audit, title=title.strip(), **fields)
    issue.full_clean()
    issue.save()
    return issue


@transaction.atomic
def set_issue_status(*, issue: TechnicalIssue, status: str, actor) -> TechnicalIssue:  # noqa: ANN001
    _require(actor, issue.audit.organization)

    if status not in IssueStatus.values:
        raise ValidationError(f"{status!r} is not an issue status.")

    issue.status = status
    fields = ["status", "updated_at"]

    # Stamped when it is actually fixed, cleared if it is reopened — so
    # "when was this resolved?" never contradicts the status beside it.
    if status == IssueStatus.FIXED and issue.resolved_on is None:
        issue.resolved_on = timezone.localdate()
        fields.append("resolved_on")
    elif status in {IssueStatus.OPEN, IssueStatus.IN_PROGRESS} \
            and issue.resolved_on is not None:
        issue.resolved_on = None
        fields.append("resolved_on")

    issue.save(update_fields=fields)
    return issue


# ---------------------------------------------------------------------------
# Keywords and positions
# ---------------------------------------------------------------------------


@transaction.atomic
def add_keyword(*, organization, term: str, actor, **fields) -> Keyword:  # noqa: ANN001
    _require(actor, organization, action="create")

    keyword = Keyword(organization=organization, term=term.strip(), **fields)
    keyword.full_clean()
    keyword.save()
    return keyword


@transaction.atomic
def record_position(*, keyword: Keyword, recorded_on, position, actor,  # noqa: ANN001
                    source: str = "") -> KeywordRanking:
    """Record where a keyword sat on a date.

    One reading per keyword per day: a second reading for the same date
    replaces the first rather than creating a duplicate the charts would
    have to choose between.
    """
    _require(actor, keyword.organization)

    ranking, _created = KeywordRanking.objects.update_or_create(
        keyword=keyword, recorded_on=recorded_on,
        defaults={"position": position, "source": source[:120]},
    )
    return ranking


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@transaction.atomic
def create_task(*, organization, title: str, actor, **fields) -> SeoTask:  # noqa: ANN001
    _require(actor, organization, action="create")

    task = SeoTask(organization=organization, title=title.strip(), **fields)
    task.full_clean()
    task.save()
    return task


@transaction.atomic
def update_task(*, task: SeoTask, actor, **fields) -> SeoTask:  # noqa: ANN001
    _require(actor, task.organization)

    editable = {"title", "kind", "status", "detail", "client_summary",
                "assigned_to", "due_on", "delivered_url", "campaign",
                "keyword", "issue"}
    changed = [field for field, value in fields.items()
               if field in editable and getattr(task, field) != value]
    for field in changed:
        setattr(task, field, fields[field])

    if not changed:
        return task

    # Completion is stamped from the status rather than typed, so the two
    # cannot disagree.
    if task.status == TaskStatus.DONE and task.completed_on is None:
        task.completed_on = timezone.localdate()
        changed.append("completed_on")
    elif task.status != TaskStatus.DONE and task.completed_on is not None:
        task.completed_on = None
        changed.append("completed_on")

    task.full_clean()
    task.save(update_fields=[*changed, "updated_at"])
    return task


# ---------------------------------------------------------------------------
# Backlinks
# ---------------------------------------------------------------------------


@transaction.atomic
def record_backlink(*, organization, source_domain: str, actor,  # noqa: ANN001
                    **fields) -> Backlink:
    _require(actor, organization, action="create")

    link = Backlink(organization=organization,
                    source_domain=source_domain.strip(), **fields)
    link.full_clean()
    link.save()
    return link


@transaction.atomic
def update_backlink(*, backlink: Backlink, actor, **fields) -> Backlink:  # noqa: ANN001
    _require(actor, backlink.organization)

    editable = {"source_domain", "source_url", "target_url", "anchor_text",
                "status", "authority", "is_follow", "contacted_on",
                "went_live_on", "notes", "campaign"}
    changed = [field for field, value in fields.items()
               if field in editable and getattr(backlink, field) != value]
    for field in changed:
        setattr(backlink, field, fields[field])

    if not changed:
        return backlink

    if backlink.status == BacklinkStatus.LIVE and backlink.went_live_on is None:
        backlink.went_live_on = timezone.localdate()
        changed.append("went_live_on")

    backlink.full_clean()
    backlink.save(update_fields=[*changed, "updated_at"])
    return backlink


# ---------------------------------------------------------------------------
# Progress updates
# ---------------------------------------------------------------------------


@transaction.atomic
def post_progress_update(*, campaign, body: str, actor,  # noqa: ANN001
                         is_internal: bool = False):  # noqa: ANN201
    """A progress note on an SEO campaign.

    Deliberately delegated to the campaign engine rather than given a
    model here. A campaign already has an append-only timeline with an
    internal flag on every entry; a second one for SEO would need its own
    permission rules and would be the obvious place for an internal note
    to leak.
    """
    from apps.campaigns.services import add_note

    return add_note(campaign=campaign, body=body, actor=actor,
                    is_internal=is_internal)


# ---------------------------------------------------------------------------
# Telling the client
# ---------------------------------------------------------------------------


def _notify_client(organization, *, title: str, body: str = "") -> None:  # noqa: ANN001
    """In-app, to that organization's own people and nobody else."""
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import notify
    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    members = (
        OrganizationMember.objects
        .filter(organization=organization,
                status__in=ACTIVE_MEMBERSHIP_STATUSES)
        .select_related("user")
    )
    for member in members:
        notify(recipient=member.user, title=title, body=body,
               url="/organization/area/seo/",
               level=NotificationLevel.INFO, category="seo")
