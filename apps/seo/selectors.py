"""Read access for the SEO domain.

Every queryset is scoped to the requesting actor before it leaves this
module. Views and templates read through these functions, never a raw
manager, so the isolation rule stays in one place.

The summary functions here are what the workspace's KPI cards are built
from. All of them count records this platform actually holds — none
estimates, models or fetches anything.
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.seo import policies
from apps.seo.models import (
    Backlink,
    BacklinkStatus,
    GoalMetric,
    IssueStatus,
    Keyword,
    SeoAudit,
    SeoGoal,
    SeoTask,
    TaskKind,
    TaskStatus,
    TechnicalIssue,
)


def _scoped(queryset, actor):  # noqa: ANN001, ANN202
    """Tenancy, then assignment.

    `visible_to` says which rows belong to clients this actor may see at
    all; `scope_to_accessible` narrows staff to the clients they are
    assigned to. Skipping the second is how a list becomes a quiet way
    round every object-level check.
    """
    from apps.permissions.guards import scope_to_accessible

    return scope_to_accessible(queryset.visible_to(actor), actor,
                               field="organization_id")


# ---------------------------------------------------------------------------
# Audits and issues
# ---------------------------------------------------------------------------


def visible_audits(actor, *, organization=None, status: str = "",  # noqa: ANN001
                   search: str = "") -> QuerySet:
    if not policies.can_view_seo(actor):
        return SeoAudit.objects.none()

    queryset = _scoped(SeoAudit.objects, actor).select_related(
        "organization", "performed_by",
    ).annotate(
        issue_count=Count("issues", distinct=True),
        open_issue_count=Count(
            "issues", filter=Q(issues__status__in=[IssueStatus.OPEN,
                                                   IssueStatus.IN_PROGRESS]),
            distinct=True,
        ),
    )

    if organization is not None:
        queryset = queryset.filter(organization=organization)
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(organization__name__icontains=search)
        )

    return queryset


def get_audit(actor, pk: int):  # noqa: ANN001, ANN201
    """One audit, through the same rule that filters the list.

    A guessed id is refused by the isolation rule rather than by the
    template, and a 404 — not a 403 — comes back: confirming another
    client's audit exists is itself information.
    """
    return visible_audits(actor).prefetch_related("issues").filter(pk=pk).first()


def issues_for(audit, *, status: str = "") -> list:  # noqa: ANN001
    """An audit's findings, worst first.

    Sorted in Python over an already-prefetched relation: severity is a
    string in the database, and ordering by it alphabetically would put
    "critical" after "high" and below "low".
    """
    issues = list(audit.issues.all())
    if status:
        issues = [issue for issue in issues if issue.status == status]
    return sorted(issues, key=lambda issue: (issue.severity_rank, issue.order,
                                             issue.pk))


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


def visible_keywords(actor, *, organization=None, tracked_only: bool = True,  # noqa: ANN001
                     search: str = "") -> QuerySet:
    if not policies.can_view_seo(actor):
        return Keyword.objects.none()

    queryset = _scoped(Keyword.objects, actor).select_related("organization")
    queryset = queryset.with_latest()

    if organization is not None:
        queryset = queryset.filter(organization=organization)
    if tracked_only:
        queryset = queryset.filter(is_tracked=True)
    if search:
        queryset = queryset.filter(term__icontains=search)

    return queryset


def get_keyword(actor, pk: int):  # noqa: ANN001, ANN201
    return (
        visible_keywords(actor, tracked_only=False)
        .prefetch_related("rankings")
        .filter(pk=pk)
        .first()
    )


def ranking_history(keyword, *, limit: int = 60) -> list:  # noqa: ANN001
    """Recorded positions, oldest first, for drawing a line.

    Oldest first because that is the direction a chart reads; the model
    orders newest first because that is the direction a list reads.
    """
    rows = list(keyword.rankings.order_by("-recorded_on")[:limit])
    return list(reversed(rows))


# ---------------------------------------------------------------------------
# Tasks and links
# ---------------------------------------------------------------------------


def visible_tasks(actor, *, organization=None, kind: str = "",  # noqa: ANN001
                  status: str = "", search: str = "") -> QuerySet:
    if not policies.can_view_seo(actor):
        return SeoTask.objects.none()

    queryset = _scoped(SeoTask.objects, actor).select_related(
        "organization", "assigned_to", "keyword",
    )

    if organization is not None:
        queryset = queryset.filter(organization=organization)
    if kind:
        queryset = queryset.filter(kind=kind)
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Q(detail__icontains=search)
        )

    return queryset


def get_task(actor, pk: int):  # noqa: ANN001, ANN201
    return visible_tasks(actor).filter(pk=pk).first()


def visible_backlinks(actor, *, organization=None, status: str = "",  # noqa: ANN001
                      search: str = "") -> QuerySet:
    if not policies.can_view_seo(actor):
        return Backlink.objects.none()

    queryset = _scoped(Backlink.objects, actor).select_related("organization")

    if organization is not None:
        queryset = queryset.filter(organization=organization)
    if status:
        queryset = queryset.filter(status=status)
    if search:
        queryset = queryset.filter(
            Q(source_domain__icontains=search) | Q(anchor_text__icontains=search)
        )

    return queryset


def get_backlink(actor, pk: int):  # noqa: ANN001, ANN201
    return visible_backlinks(actor).filter(pk=pk).first()


# ---------------------------------------------------------------------------
# Goals, measured from what is actually recorded
# ---------------------------------------------------------------------------


def _measure(organization, metric: str) -> int:
    """Where a client currently stands on one measure.

    Computed from the records this module holds rather than typed in: a
    goal whose progress is entered by hand is a goal nobody has to meet.
    """
    if metric in {GoalMetric.KEYWORDS_IN_TOP_3, GoalMetric.KEYWORDS_IN_TOP_10}:
        ceiling = 3 if metric == GoalMetric.KEYWORDS_IN_TOP_3 else 10
        keywords = Keyword.objects.filter(
            organization=organization, is_tracked=True).with_latest()
        return sum(
            1 for keyword in keywords
            if keyword.latest_position and keyword.latest_position <= ceiling
        )

    if metric == GoalMetric.ISSUES_RESOLVED:
        return TechnicalIssue.objects.filter(
            audit__organization=organization, status=IssueStatus.FIXED).count()

    if metric == GoalMetric.LIVE_BACKLINKS:
        return Backlink.objects.filter(
            organization=organization, status=BacklinkStatus.LIVE).count()

    if metric == GoalMetric.CONTENT_PUBLISHED:
        return SeoTask.objects.filter(
            organization=organization, kind=TaskKind.CONTENT,
            status=TaskStatus.DONE).exclude(delivered_url="").count()

    return 0


def goals_for(organization) -> list[dict]:  # noqa: ANN001
    """Active goals with their measured progress."""
    goals = []
    for goal in SeoGoal.objects.filter(organization=organization,
                                       is_active=True):
        current = _measure(organization, goal.metric)
        goals.append({
            "goal": goal,
            "current": current,
            "target": goal.target,
            "percent": min(100, round(current / goal.target * 100))
            if goal.target else 0,
            "met": current >= goal.target,
        })
    return goals


# ---------------------------------------------------------------------------
# The summary the workspace is built from
# ---------------------------------------------------------------------------


def summary_for(organization) -> dict:  # noqa: ANN001
    """Headline figures for one client.

    Every one is a count of records this platform holds. Nothing is
    estimated, modelled or fetched — if the agency has not recorded a
    position, there is no position here.
    """
    keywords = list(
        Keyword.objects.filter(organization=organization,
                               is_tracked=True).with_latest()
    )
    ranked = [k for k in keywords if k.latest_position]

    issues = TechnicalIssue.objects.filter(audit__organization=organization)
    tasks = SeoTask.objects.filter(organization=organization)

    return {
        "keywords_tracked": len(keywords),
        "keywords_ranked": len(ranked),
        "keywords_top_3": sum(1 for k in ranked if k.latest_position <= 3),
        "keywords_top_10": sum(1 for k in ranked if k.latest_position <= 10),
        # Averaged over the keywords that have a reading. Including the
        # unranked ones as a large number would drag the average toward a
        # figure nobody measured.
        "average_position": (
            round(sum(k.latest_position for k in ranked) / len(ranked), 1)
            if ranked else None
        ),
        "issues_open": issues.filter(
            status__in=[IssueStatus.OPEN, IssueStatus.IN_PROGRESS]).count(),
        "issues_fixed": issues.filter(status=IssueStatus.FIXED).count(),
        "issues_critical": issues.filter(
            severity="critical",
            status__in=[IssueStatus.OPEN, IssueStatus.IN_PROGRESS]).count(),
        "tasks_open": tasks.filter(status__in=[
            TaskStatus.PLANNED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW,
        ]).count(),
        "tasks_done": tasks.filter(status=TaskStatus.DONE).count(),
        "backlinks_live": Backlink.objects.filter(
            organization=organization, status=BacklinkStatus.LIVE).count(),
        "audits": SeoAudit.objects.filter(organization=organization).count(),
    }


def has_any_data(organization) -> bool:  # noqa: ANN001
    """Whether there is anything to show at all.

    Decides between a workspace and an honest empty state, rather than a
    page of zeroes that looks like a failure.
    """
    return any([
        Keyword.objects.filter(organization=organization).exists(),
        SeoAudit.objects.filter(organization=organization).exists(),
        SeoTask.objects.filter(organization=organization).exists(),
        Backlink.objects.filter(organization=organization).exists(),
    ])


# ---------------------------------------------------------------------------
# What a client sees
# ---------------------------------------------------------------------------


def client_workspace(user) -> dict:  # noqa: ANN001
    """Everything a client may see about their own SEO.

    Scoped by `visible_to` from the tenancy base throughout. An audit
    appears only once it has been delivered, and a task only once
    somebody has written a summary for them — both are deliberate: work
    in progress read as a finished finding causes exactly the
    conversation it was meant to prevent.
    """
    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, Organization

    organization = (
        Organization.objects
        .filter(memberships__user=user,
                memberships__status__in=ACTIVE_MEMBERSHIP_STATUSES)
        .first()
    )
    if organization is None:
        return {"organization": None}

    keywords = sorted(
        Keyword.objects.filter(organization=organization,
                               is_tracked=True).with_latest(),
        key=lambda k: (k.latest_position is None, k.latest_position or 0,
                       k.priority),
    )

    return {
        "organization": organization,
        "summary": summary_for(organization),
        "goals": goals_for(organization),
        "keywords": keywords,
        "audits": SeoAudit.objects.filter(
            organization=organization, status="delivered"
        ).annotate(issue_count=Count("issues")),
        "tasks": SeoTask.objects.filter(organization=organization)
        .exclude(client_summary="")
        .order_by("-completed_on", "due_on")[:12],
        "backlinks": Backlink.objects.filter(
            organization=organization, status=BacklinkStatus.LIVE
        ).order_by("-went_live_on")[:10],
    }
