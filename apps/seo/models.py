"""Persistence for the SEO domain.

The first service module, and therefore the first proof that the campaign
engine's extension point works: `SeoCampaignDetail` attaches search
fields to a shared `Campaign` rather than growing a parallel campaign
table. Everything the client sees about SEO campaigns — status, budget,
owner, timeline, isolation — comes from the core.

Two of the brief's concepts deliberately have no model here:

* **Progress update** is a `CampaignEvent`. A campaign already has an
  append-only timeline with an internal/client-visible flag on every
  entry; a second one for SEO would need its own permission rules and
  would be the obvious place for an internal note to leak.
* **Report item** waits for the reports module. Inventing a reporting
  schema inside SEO would be the "unrelated architecture" the last phase
  was written to prevent.

Everything here is entered by hand or imported from a file. Nothing calls
a search engine: a number this platform did not fetch is a number it must
not pretend to have.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.campaigns.models import CampaignDetail
from apps.core.models import TimeStampedModel
from apps.organizations.models import OrganizationOwnedModel, OrganizationOwnedQuerySet

# ---------------------------------------------------------------------------
# The campaign extension
# ---------------------------------------------------------------------------


class SeoCampaignDetail(CampaignDetail):
    """Search fields attached to a shared campaign.

    This is the whole point of `apps.campaigns.registry`: SEO adds what
    it needs and inherits everything else.
    """

    focus = models.TextField(
        _("what this campaign is focused on"), blank=True,
        help_text=_("The themes or page groups being worked on. One per "
                    "line."),
    )
    competitors = models.TextField(
        _("competitors watched"), blank=True,
        help_text=_("One domain per line. Used for context in reporting, "
                    "not fetched from anywhere."),
    )
    audit = models.ForeignKey(
        "seo.SeoAudit", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="campaigns", verbose_name=_("from audit"),
        help_text=_("The audit this campaign is working through, where "
                    "there is one."),
    )

    class Meta:
        verbose_name = _("SEO campaign detail")
        verbose_name_plural = _("SEO campaign details")

    def __str__(self) -> str:
        return f"SEO detail for {self.campaign_id}"

    @property
    def focus_lines(self) -> list[str]:
        return [line.strip() for line in self.focus.splitlines() if line.strip()]

    @property
    def competitor_lines(self) -> list[str]:
        return [line.strip() for line in self.competitors.splitlines()
                if line.strip()]


# ---------------------------------------------------------------------------
# Audits and what they find
# ---------------------------------------------------------------------------


class AuditStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", _("In progress")
    DELIVERED = "delivered", _("Delivered")
    ARCHIVED = "archived", _("Archived")


class SeoAudit(OrganizationOwnedModel, TimeStampedModel):
    """A point-in-time review of a client's site.

    Scores are entered by whoever ran the audit, with a note saying where
    each came from. They are not fetched: a figure this platform did not
    measure is one it must not present as its own.
    """

    title = models.CharField(_("title"), max_length=200,
                             help_text=_("For example, “Technical audit, "
                                         "March 2026”."))
    site_url = models.URLField(_("site audited"), max_length=300, blank=True)
    performed_on = models.DateField(_("carried out"), default=timezone.localdate)

    status = models.CharField(_("status"), max_length=20,
                              choices=AuditStatus.choices,
                              default=AuditStatus.IN_PROGRESS, db_index=True)

    summary = models.TextField(
        _("summary for the client"), blank=True,
        help_text=_("What the audit found, in plain language. Shown in "
                    "their workspace once delivered."),
    )
    internal_notes = models.TextField(
        _("internal notes"), blank=True,
        help_text=_("Staff only. The client never sees this."),
    )

    #: Headline scores, recorded by hand. Nullable because an audit may
    #: legitimately not measure one of them, and a zero would read as a
    #: catastrophic result rather than as a gap.
    health_score = models.PositiveSmallIntegerField(
        _("technical health"), null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Out of 100, as you assessed it. Say where it came "
                    "from in the source note."),
    )
    pages_crawled = models.PositiveIntegerField(_("pages crawled"), null=True,
                                                blank=True)
    score_source = models.CharField(
        _("where the figures came from"), max_length=200, blank=True,
        help_text=_("The tool or method behind the numbers above. Recorded "
                    "so nobody has to guess later."),
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="seo_audits", verbose_name=_("carried out by"),
    )

    objects = OrganizationOwnedQuerySet.as_manager()

    class Meta:
        verbose_name = _("SEO audit")
        verbose_name_plural = _("SEO audits")
        ordering = ["-performed_on", "-pk"]
        indexes = [
            models.Index(fields=["organization", "-performed_on"],
                         name="seoaudit_org_date_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("staff:seo_audit_detail", kwargs={"pk": self.pk})

    @property
    def is_delivered(self) -> bool:
        return self.status == AuditStatus.DELIVERED


class IssueSeverity(models.TextChoices):
    CRITICAL = "critical", _("Critical")
    HIGH = "high", _("High")
    MEDIUM = "medium", _("Medium")
    LOW = "low", _("Low")


class IssueStatus(models.TextChoices):
    OPEN = "open", _("Open")
    IN_PROGRESS = "in_progress", _("Being fixed")
    FIXED = "fixed", _("Fixed")
    WONT_FIX = "wont_fix", _("Will not fix")


#: Severities ordered worst-first, so a list sorts the way somebody
#: triaging it expects rather than alphabetically.
SEVERITY_ORDER = {
    IssueSeverity.CRITICAL: 0, IssueSeverity.HIGH: 1,
    IssueSeverity.MEDIUM: 2, IssueSeverity.LOW: 3,
}


class TechnicalIssue(TimeStampedModel):
    """One finding from an audit.

    Reached through its audit for isolation — which is how the tenancy
    guard traces it to an owner without denormalising the organization
    onto every row.
    """

    audit = models.ForeignKey(SeoAudit, on_delete=models.CASCADE,
                              related_name="issues", verbose_name=_("audit"))

    title = models.CharField(_("issue"), max_length=250)
    detail = models.TextField(_("detail"), blank=True,
                              help_text=_("What is wrong and why it matters."))
    recommendation = models.TextField(
        _("what to do"), blank=True,
        help_text=_("The fix, written so a developer can act on it."),
    )

    severity = models.CharField(_("severity"), max_length=20,
                                choices=IssueSeverity.choices,
                                default=IssueSeverity.MEDIUM, db_index=True)
    status = models.CharField(_("status"), max_length=20,
                              choices=IssueStatus.choices,
                              default=IssueStatus.OPEN, db_index=True)

    affected_urls = models.TextField(
        _("affected pages"), blank=True,
        help_text=_("One URL per line."),
    )
    pages_affected = models.PositiveIntegerField(
        _("how many pages"), null=True, blank=True,
        help_text=_("Where it is more than you would list."),
    )

    resolved_on = models.DateField(_("fixed on"), null=True, blank=True)
    order = models.PositiveIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("technical issue")
        verbose_name_plural = _("technical issues")
        ordering = ["order", "pk"]
        indexes = [
            models.Index(fields=["audit", "severity"],
                         name="seoissue_audit_sev_idx"),
            models.Index(fields=["status"], name="seoissue_status_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_resolved(self) -> bool:
        return self.status in {IssueStatus.FIXED, IssueStatus.WONT_FIX}

    @property
    def severity_rank(self) -> int:
        return SEVERITY_ORDER.get(self.severity, 9)

    @property
    def url_lines(self) -> list[str]:
        return [line.strip() for line in self.affected_urls.splitlines()
                if line.strip()]


# ---------------------------------------------------------------------------
# Keywords and where they rank
# ---------------------------------------------------------------------------


class KeywordQuerySet(OrganizationOwnedQuerySet):
    def tracked(self) -> models.QuerySet:
        return self.filter(is_tracked=True)

    def with_latest(self) -> models.QuerySet:
        """Keywords with their most recent recorded position attached.

        A subquery rather than a join, so a hundred keywords stay one
        query instead of becoming a hundred and one.
        """
        from django.db.models import OuterRef, Subquery

        latest = KeywordRanking.objects.filter(
            keyword=OuterRef("pk")).order_by("-recorded_on")

        return self.annotate(
            latest_position=Subquery(latest.values("position")[:1]),
            latest_recorded_on=Subquery(latest.values("recorded_on")[:1]),
        )


class Keyword(OrganizationOwnedModel, TimeStampedModel):
    """A search term tracked for a client.

    Positions are recorded against it over time, by hand or from a file.
    Nothing here queries a search engine.
    """

    term = models.CharField(_("search term"), max_length=200)
    #: Which page we want to rank. Blank where it has not been decided,
    #: which is itself worth knowing.
    target_url = models.URLField(_("target page"), max_length=300, blank=True)

    search_volume = models.PositiveIntegerField(
        _("monthly searches"), null=True, blank=True,
        help_text=_("As reported by whichever tool you took it from. "
                    "Record the source on the campaign."),
    )
    difficulty = models.PositiveSmallIntegerField(
        _("difficulty"), null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    priority = models.PositiveSmallIntegerField(
        _("priority"), default=2,
        help_text=_("1 is highest. Used for ordering, nothing else."),
    )

    is_tracked = models.BooleanField(
        _("still tracked"), default=True,
        help_text=_("Turn off to stop reporting on it without losing its "
                    "history."),
    )
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="seo_keywords", verbose_name=_("campaign"),
    )

    objects = KeywordQuerySet.as_manager()

    class Meta:
        verbose_name = _("keyword")
        verbose_name_plural = _("keywords")
        ordering = ["priority", "term"]
        constraints = [
            # The same term tracked twice for one client splits its
            # history in two and makes every chart wrong.
            models.UniqueConstraint(fields=["organization", "term"],
                                    name="one_keyword_per_client"),
        ]
        indexes = [
            models.Index(fields=["organization", "is_tracked"],
                         name="seokw_org_tracked_idx"),
        ]

    def __str__(self) -> str:
        return self.term

    @property
    def latest(self):  # noqa: ANN201
        return self.rankings.order_by("-recorded_on").first()


class KeywordRanking(models.Model):
    """Where a keyword sat on a given day.

    One row per keyword per date. Entered by hand or imported from a CSV
    export — there is no live integration, by design.

    Deliberately not `TimeStampedModel`: `recorded_on` is the date the
    position was *observed*, which is the only date that means anything
    here, and a second "created" timestamp invites the two to be confused.
    """

    keyword = models.ForeignKey(Keyword, on_delete=models.CASCADE,
                                related_name="rankings",
                                verbose_name=_("keyword"))
    recorded_on = models.DateField(_("observed on"), db_index=True)
    position = models.PositiveSmallIntegerField(
        _("position"), null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(200)],
        help_text=_("Leave blank for “not in the top 200”, which is "
                    "different from position zero."),
    )
    source = models.CharField(
        _("source"), max_length=120, blank=True,
        help_text=_("Where this reading came from. Kept so a figure can "
                    "always be traced back."),
    )

    class Meta:
        verbose_name = _("keyword position")
        verbose_name_plural = _("keyword positions")
        ordering = ["-recorded_on"]
        constraints = [
            models.UniqueConstraint(fields=["keyword", "recorded_on"],
                                    name="one_reading_per_keyword_per_day"),
        ]

    def __str__(self) -> str:
        return f"{self.keyword_id} on {self.recorded_on}"


# ---------------------------------------------------------------------------
# Work: content, technical fixes and outreach
# ---------------------------------------------------------------------------


class TaskKind(models.TextChoices):
    CONTENT = "content", _("Content")
    TECHNICAL = "technical", _("Technical")
    OUTREACH = "outreach", _("Outreach")
    OTHER = "other", _("Other")


class TaskStatus(models.TextChoices):
    PLANNED = "planned", _("Planned")
    IN_PROGRESS = "in_progress", _("In progress")
    REVIEW = "review", _("In review")
    DONE = "done", _("Done")
    CANCELLED = "cancelled", _("Cancelled")


OPEN_TASK_STATUSES = frozenset({
    TaskStatus.PLANNED, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW,
})


class SeoTask(OrganizationOwnedModel, TimeStampedModel):
    """A piece of SEO work.

    One model for content, technical and outreach work rather than three,
    because they differ in `kind` and in nothing else that matters: all
    have an owner, a due date, a status and something handed over at the
    end.

    A **deliverable** in the brief's sense is a finished task with a
    `delivered_url` — the thing the client actually receives. Giving that
    its own table would have meant keeping two statuses in step for one
    piece of work.
    """

    title = models.CharField(_("task"), max_length=250)
    kind = models.CharField(_("kind"), max_length=20, choices=TaskKind.choices,
                            default=TaskKind.CONTENT, db_index=True)
    status = models.CharField(_("status"), max_length=20,
                              choices=TaskStatus.choices,
                              default=TaskStatus.PLANNED, db_index=True)

    detail = models.TextField(_("detail"), blank=True)
    client_summary = models.CharField(
        _("summary for the client"), max_length=300, blank=True,
        help_text=_("Shown in their workspace. Leave blank to keep this "
                    "task internal."),
    )

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="seo_tasks", verbose_name=_("campaign"),
    )
    issue = models.ForeignKey(
        TechnicalIssue, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tasks", verbose_name=_("fixes issue"),
    )
    keyword = models.ForeignKey(
        Keyword, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="tasks", verbose_name=_("targets keyword"),
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="seo_tasks", verbose_name=_("assigned to"),
    )
    due_on = models.DateField(_("due"), null=True, blank=True)
    completed_on = models.DateField(_("completed"), null=True, blank=True)

    delivered_url = models.URLField(
        _("where it landed"), max_length=300, blank=True,
        help_text=_("The published page, document or link. This is what "
                    "makes a finished task a deliverable."),
    )

    objects = OrganizationOwnedQuerySet.as_manager()

    class Meta:
        verbose_name = _("SEO task")
        verbose_name_plural = _("SEO tasks")
        ordering = ["due_on", "-pk"]
        indexes = [
            models.Index(fields=["organization", "status"],
                         name="seotask_org_status_idx"),
            models.Index(fields=["kind", "status"], name="seotask_kind_idx"),
            models.Index(fields=["due_on"], name="seotask_due_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_TASK_STATUSES

    @property
    def is_deliverable(self) -> bool:
        """A finished task the client actually receives something from."""
        return self.status == TaskStatus.DONE and bool(self.delivered_url)

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_on and self.is_open
                    and self.due_on < timezone.localdate())


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


class BacklinkStatus(models.TextChoices):
    PROSPECT = "prospect", _("Prospect")
    CONTACTED = "contacted", _("Contacted")
    AGREED = "agreed", _("Agreed")
    LIVE = "live", _("Live")
    LOST = "lost", _("Lost")
    REJECTED = "rejected", _("Rejected")


class Backlink(OrganizationOwnedModel, TimeStampedModel):
    """One link, from prospect through to live.

    Outreach and the link it produces are the same record at different
    stages. Splitting them would mean reconciling two tables to answer
    "did that outreach ever land?".
    """

    source_domain = models.CharField(_("from"), max_length=200,
                                     help_text=_("The site linking to you."))
    source_url = models.URLField(_("link page"), max_length=500, blank=True,
                                 help_text=_("Where the link appears."))
    target_url = models.URLField(_("links to"), max_length=300, blank=True)
    anchor_text = models.CharField(_("anchor text"), max_length=250, blank=True)

    status = models.CharField(_("status"), max_length=20,
                              choices=BacklinkStatus.choices,
                              default=BacklinkStatus.PROSPECT, db_index=True)

    authority = models.PositiveSmallIntegerField(
        _("authority"), null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("Whatever authority metric you use. Note the source on "
                    "the campaign — it is not fetched."),
    )
    is_follow = models.BooleanField(_("followed"), default=True)

    contacted_on = models.DateField(_("contacted"), null=True, blank=True)
    went_live_on = models.DateField(_("went live"), null=True, blank=True)

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="seo_backlinks", verbose_name=_("campaign"),
    )
    notes = models.TextField(_("internal notes"), blank=True,
                             help_text=_("Staff only."))

    objects = OrganizationOwnedQuerySet.as_manager()

    class Meta:
        verbose_name = _("backlink")
        verbose_name_plural = _("backlinks")
        ordering = ["-went_live_on", "-pk"]
        indexes = [
            models.Index(fields=["organization", "status"],
                         name="seolink_org_status_idx"),
        ]

    def __str__(self) -> str:
        return self.source_domain

    @property
    def is_live(self) -> bool:
        return self.status == BacklinkStatus.LIVE


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------


class GoalMetric(models.TextChoices):
    KEYWORDS_IN_TOP_3 = "top_3", _("Keywords in the top 3")
    KEYWORDS_IN_TOP_10 = "top_10", _("Keywords in the top 10")
    ISSUES_RESOLVED = "issues_resolved", _("Technical issues resolved")
    LIVE_BACKLINKS = "live_backlinks", _("Live backlinks")
    CONTENT_PUBLISHED = "content_published", _("Content pieces published")


class SeoGoal(OrganizationOwnedModel, TimeStampedModel):
    """A target the agency has agreed with a client.

    Progress is **computed** from the records this module already holds,
    not typed in: a goal whose progress is entered by hand is a goal
    nobody has to meet.
    """

    metric = models.CharField(_("measure"), max_length=30,
                              choices=GoalMetric.choices)
    target = models.PositiveIntegerField(_("target"))
    due_on = models.DateField(_("by"), null=True, blank=True)

    note = models.CharField(
        _("note"), max_length=250, blank=True,
        help_text=_("Shown to the client beside the goal."),
    )
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="seo_goals", verbose_name=_("campaign"),
    )
    is_active = models.BooleanField(_("active"), default=True)

    objects = OrganizationOwnedQuerySet.as_manager()

    class Meta:
        verbose_name = _("SEO goal")
        verbose_name_plural = _("SEO goals")
        ordering = ["due_on", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "metric"],
                condition=models.Q(is_active=True),
                name="one_active_goal_per_metric",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_metric_display()}: {self.target}"

    def clean(self) -> None:
        super().clean()
        if self.target == 0:
            raise ValidationError({"target": _("A target of zero is not a goal.")})
