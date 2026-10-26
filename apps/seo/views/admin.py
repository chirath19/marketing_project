"""Staff management of SEO records.

The workspace is per client: SEO work is only meaningful against one
site, so these pages hang off a client rather than listing every
keyword the agency tracks for everybody.

Every route is guarded twice: `@require_permission` opens the page, and
the service layer re-checks the permission **against the client the
record belongs to** before anything changes.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.permissions.guards import require_permission
from apps.seo import selectors, services
from apps.seo.forms import (
    AuditForm,
    BacklinkForm,
    IssueForm,
    KeywordForm,
    KeywordImportForm,
    PositionForm,
    TaskForm,
)
from apps.seo.models import IssueStatus, TaskKind, TaskStatus


def _client(request: HttpRequest, slug: str):  # noqa: ANN202
    """The client this page is about, or a 404.

    Both halves of the rule, in one place. `get_organization` answers
    "does this organization exist and is it visible at all" — it does
    **not** apply client assignments, which was the bug this helper was
    first written with: a specialist assigned to one client could open
    another client's SEO workspace by typing its slug.

    `access.can` is the documented rule: the permission for the action
    **and** access to that client. A 404 rather than a 403, because
    confirming another client exists is itself information.
    """
    from apps.organizations import selectors as organization_selectors
    from apps.permissions import access

    organization = organization_selectors.get_organization(request.user, slug)
    if organization is None:
        raise Http404("No such client.")

    if not access.can(request.user, "permissions.seo_view", organization):
        raise Http404("No such client.")

    return organization


def _shell(organization, title: str, subtitle: str = "", *,  # noqa: ANN001
           section: str = "overview", **extra) -> dict:
    return {
        "page_title": title, "page_subtitle": subtitle, "nav_key": "seo",
        "organization": organization, "section": section,
        "breadcrumbs": [
            {"label": "SEO", "href": "/staff/seo/"},
            {"label": organization.label,
             "href": f"/staff/seo/{organization.slug}/"},
        ],
        **extra,
    }


# ---------------------------------------------------------------------------
# Choosing a client
# ---------------------------------------------------------------------------


@require_permission("seo_view")
def seo_home(request: HttpRequest) -> HttpResponse:
    """Clients with SEO work, so staff pick a site before anything else."""
    from apps.organizations import selectors as organization_selectors
    from apps.permissions.guards import scope_to_accessible

    organizations = scope_to_accessible(
        organization_selectors.visible_organizations(request.user).order_by("name"),
        request.user, field="id",
    )

    rows = [
        {"organization": organization,
         "summary": selectors.summary_for(organization)}
        for organization in organizations
    ]
    # Clients with nothing recorded sink to the bottom rather than
    # cluttering the top of a list somebody is scanning for live work.
    rows.sort(key=lambda row: (
        row["summary"]["keywords_tracked"] == 0,
        -row["summary"]["issues_open"],
    ))

    return render(request, "seo/admin/home.html", {
        "page_title": "SEO",
        "page_subtitle": "Search work, per client.",
        "nav_key": "seo",
        "rows": rows,
    })


@require_permission("seo_view")
def client_workspace(request: HttpRequest, slug: str) -> HttpResponse:
    """One client's SEO workspace: the summary, and the way in to each part."""
    organization = _client(request, slug)

    audits = selectors.visible_audits(request.user, organization=organization)
    keywords = selectors.visible_keywords(request.user, organization=organization)

    return render(request, "seo/admin/workspace.html", _shell(
        organization, f"SEO — {organization.label}",
        "Everything recorded for this site. Nothing here is fetched from a "
        "search engine.",
        summary=selectors.summary_for(organization),
        goals=selectors.goals_for(organization),
        audits=audits[:5],
        keywords=sorted(
            keywords,
            key=lambda k: (k.latest_position is None, k.latest_position or 0),
        )[:10],
        tasks=selectors.visible_tasks(
            request.user, organization=organization,
        ).exclude(status__in=[TaskStatus.DONE, TaskStatus.CANCELLED])[:8],
        backlinks=selectors.visible_backlinks(
            request.user, organization=organization,
        )[:8],
        has_data=selectors.has_any_data(organization),
    ))


# ---------------------------------------------------------------------------
# Audits
# ---------------------------------------------------------------------------


@require_permission("seo_view")
def audit_list(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)

    return render(request, "seo/admin/audits.html", _shell(
        organization, f"Audits — {organization.label}",
        "Point-in-time reviews of this site.", section="audits",
        audits=selectors.visible_audits(request.user, organization=organization),
        columns=[{"label": "Audit"}, {"label": "Findings"},
                 {"label": "Health"}, {"label": "Status"}],
        form=AuditForm(),
        can_create=request.user.has_perm("permissions.seo_create", organization),
    ))


@require_permission("seo_create")
@require_http_methods(["POST"])
def audit_create(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)
    form = AuditForm(request.POST)

    if form.is_valid():
        try:
            audit = services.create_audit(
                organization=organization, actor=request.user,
                **form.cleaned_data,
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Audit created."))
            return redirect("staff:seo_audit_detail", pk=audit.pk)
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_audits", slug=slug)


def _audit_or_404(request: HttpRequest, pk: int):  # noqa: ANN202
    audit = selectors.get_audit(request.user, pk)
    if audit is None:
        # 404 rather than 403: confirming another client's audit exists
        # is itself information.
        raise Http404("No such audit.")
    return audit


@require_permission("seo_view")
def audit_detail(request: HttpRequest, pk: int) -> HttpResponse:
    audit = _audit_or_404(request, pk)
    issues = selectors.issues_for(audit)

    return render(request, "seo/admin/audit_detail.html", _shell(
        audit.organization, audit.title,
        f"Carried out {audit.performed_on:%-d %B %Y}", section="audits",
        audit=audit, issues=issues,
        open_issues=[issue for issue in issues if not issue.is_resolved],
        form=AuditForm.for_audit(audit),
        issue_form=IssueForm(),
        issue_statuses=IssueStatus.choices,
        can_edit=request.user.has_perm("permissions.seo_edit",
                                       audit.organization),
        can_deliver=request.user.has_perm("permissions.seo_approve",
                                          audit.organization),
    ))


@require_permission("seo_edit")
@require_http_methods(["POST"])
def audit_update(request: HttpRequest, pk: int) -> HttpResponse:
    audit = _audit_or_404(request, pk)
    form = AuditForm(request.POST)

    if form.is_valid():
        services.update_audit(audit=audit, actor=request.user,
                              **form.cleaned_data)
        messages.success(request, _("Audit updated."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_audit_detail", pk=pk)


@require_permission("seo_view")
@require_http_methods(["POST"])
def audit_deliver(request: HttpRequest, pk: int) -> HttpResponse:
    """Publish the audit to the client.

    Guarded at `view` here and at `approve` in the service layer, against
    this client — so the rule holds for every caller.
    """
    audit = _audit_or_404(request, pk)

    try:
        services.deliver_audit(audit=audit, actor=request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    except PermissionDenied:
        messages.error(request, _("You may not deliver audits."))
    else:
        messages.success(
            request, _("Delivered. The client can see it in their workspace."))

    return redirect("staff:seo_audit_detail", pk=pk)


@require_permission("seo_edit")
@require_http_methods(["POST"])
def issue_create(request: HttpRequest, pk: int) -> HttpResponse:
    audit = _audit_or_404(request, pk)
    form = IssueForm(request.POST)

    if form.is_valid():
        services.add_issue(audit=audit, actor=request.user, **form.cleaned_data)
        messages.success(request, _("Finding added."))
    else:
        messages.error(request, _("A finding needs at least a title."))

    return redirect("staff:seo_audit_detail", pk=pk)


@require_permission("seo_edit")
@require_http_methods(["POST"])
def issue_status(request: HttpRequest, pk: int) -> HttpResponse:
    from apps.seo.models import TechnicalIssue

    issue = (
        TechnicalIssue.objects.select_related("audit__organization")
        .filter(pk=pk).first()
    )
    if issue is None or selectors.get_audit(request.user,
                                            issue.audit_id) is None:
        raise Http404("No such finding.")

    try:
        services.set_issue_status(issue=issue,
                                  status=request.POST.get("status", ""),
                                  actor=request.user)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, _("Finding updated."))

    return redirect("staff:seo_audit_detail", pk=issue.audit_id)


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


@require_permission("seo_view")
def keyword_list(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)
    search = (request.GET.get("q") or "").strip()
    show_all = request.GET.get("all") == "1"

    keywords = sorted(
        selectors.visible_keywords(request.user, organization=organization,
                                   tracked_only=not show_all, search=search),
        key=lambda k: (k.latest_position is None, k.latest_position or 0,
                       k.priority),
    )

    return render(request, "seo/admin/keywords.html", _shell(
        organization, f"Keywords — {organization.label}",
        "Positions are entered by hand or imported from a file. Nothing is "
        "fetched from a search engine.", section="keywords",
        keywords=keywords, search=search, show_all=show_all,
        keyword_columns=[{"label": "Term"},
                         {"label": "Position", "align": "right"},
                         {"label": "Volume", "align": "right"},
                         {"label": "Priority", "align": "right"}],
        form=KeywordForm(), import_form=KeywordImportForm(),
        can_create=request.user.has_perm("permissions.seo_create", organization),
    ))


@require_permission("seo_create")
@require_http_methods(["POST"])
def keyword_create(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)
    form = KeywordForm(request.POST)

    if form.is_valid():
        try:
            services.add_keyword(organization=organization, actor=request.user,
                                 **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Keyword added."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_keywords", slug=slug)


@require_permission("seo_create")
@require_http_methods(["POST"])
def keyword_import(request: HttpRequest, slug: str) -> HttpResponse:
    """Import positions from a rank tracker's CSV export."""
    organization = _client(request, slug)
    form = KeywordImportForm(request.POST, request.FILES)

    if not form.is_valid():
        messages.error(request, form.errors.as_text()[:200])
        return redirect("staff:seo_keywords", slug=slug)

    from apps.seo.importers import import_keyword_positions

    result = import_keyword_positions(
        organization=organization, actor=request.user,
        file_obj=form.cleaned_data["file"],
        source=form.cleaned_data.get("source", ""),
        recorded_on=form.cleaned_data.get("recorded_on"),
    )

    if result.did_anything:
        messages.success(request, _(
            "%(positions)s position(s) recorded, %(keywords)s new keyword(s)."
        ) % {"positions": result.positions_recorded,
             "keywords": result.keywords_created})

    if result.rows_skipped:
        # Said out loud rather than swallowed: a silently skipped row is
        # a gap in a chart nobody can explain later.
        messages.warning(request, _(
            "%(count)s row(s) skipped. %(why)s"
        ) % {"count": result.rows_skipped, "why": " ".join(result.problems)})

    if not result.did_anything and not result.rows_skipped:
        messages.info(request, _("That file had no rows to import."))

    return redirect("staff:seo_keywords", slug=slug)


def _keyword_or_404(request: HttpRequest, pk: int):  # noqa: ANN202
    keyword = selectors.get_keyword(request.user, pk)
    if keyword is None:
        raise Http404("No such keyword.")
    return keyword


@require_permission("seo_view")
def keyword_detail(request: HttpRequest, pk: int) -> HttpResponse:
    keyword = _keyword_or_404(request, pk)
    history = selectors.ranking_history(keyword)

    return render(request, "seo/admin/keyword_detail.html", _shell(
        keyword.organization, keyword.term,
        "Every reading recorded for this term.", section="keywords",
        keyword=keyword, history=history,
        form=PositionForm(),
        can_edit=request.user.has_perm("permissions.seo_edit",
                                       keyword.organization),
    ))


@require_permission("seo_edit")
@require_http_methods(["POST"])
def position_record(request: HttpRequest, pk: int) -> HttpResponse:
    keyword = _keyword_or_404(request, pk)
    form = PositionForm(request.POST)

    if form.is_valid():
        services.record_position(keyword=keyword, actor=request.user,
                                 **form.cleaned_data)
        messages.success(request, _("Position recorded."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_keyword_detail", pk=pk)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@require_permission("seo_view")
def task_list(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)
    kind = request.GET.get("kind", "")
    status = request.GET.get("status", "")

    return render(request, "seo/admin/tasks.html", _shell(
        organization, f"Work — {organization.label}",
        "Content, technical fixes and outreach.", section="tasks",
        tasks=selectors.visible_tasks(request.user, organization=organization,
                                      kind=kind, status=status),
        kind=kind, status=status,
        kinds=TaskKind.choices, statuses=TaskStatus.choices,
        task_columns=[{"label": "Task"}, {"label": "Kind"},
                      {"label": "Due"}, {"label": "Status"}],
        form=TaskForm(),
        can_create=request.user.has_perm("permissions.seo_create", organization),
    ))


@require_permission("seo_create")
@require_http_methods(["POST"])
def task_create(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)
    form = TaskForm(request.POST)

    if form.is_valid():
        services.create_task(organization=organization, actor=request.user,
                             **form.cleaned_data)
        messages.success(request, _("Task added."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_tasks", slug=slug)


@require_permission("seo_edit")
@require_http_methods(["POST"])
def task_update(request: HttpRequest, pk: int) -> HttpResponse:
    task = selectors.get_task(request.user, pk)
    if task is None:
        raise Http404("No such task.")

    form = TaskForm(request.POST)
    if form.is_valid():
        services.update_task(task=task, actor=request.user, **form.cleaned_data)
        messages.success(request, _("Task updated."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_tasks", slug=task.organization.slug)


# ---------------------------------------------------------------------------
# Backlinks
# ---------------------------------------------------------------------------


@require_permission("seo_view")
def backlink_list(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)
    status = request.GET.get("status", "")

    from apps.seo.models import BacklinkStatus

    return render(request, "seo/admin/backlinks.html", _shell(
        organization, f"Links — {organization.label}",
        "Outreach and the links it produces, from prospect to live.", section="links",
        backlinks=selectors.visible_backlinks(
            request.user, organization=organization, status=status),
        status=status, statuses=BacklinkStatus.choices,
        link_columns=[{"label": "From"},
                      {"label": "Authority", "align": "right"},
                      {"label": "Dates"}, {"label": "Status"}],
        form=BacklinkForm(),
        can_create=request.user.has_perm("permissions.seo_create", organization),
    ))


@require_permission("seo_create")
@require_http_methods(["POST"])
def backlink_create(request: HttpRequest, slug: str) -> HttpResponse:
    organization = _client(request, slug)
    form = BacklinkForm(request.POST)

    if form.is_valid():
        services.record_backlink(organization=organization, actor=request.user,
                                 **form.cleaned_data)
        messages.success(request, _("Link recorded."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_backlinks", slug=slug)


@require_permission("seo_edit")
@require_http_methods(["POST"])
def backlink_update(request: HttpRequest, pk: int) -> HttpResponse:
    backlink = selectors.get_backlink(request.user, pk)
    if backlink is None:
        raise Http404("No such link.")

    form = BacklinkForm(request.POST)
    if form.is_valid():
        services.update_backlink(backlink=backlink, actor=request.user,
                                 **form.cleaned_data)
        messages.success(request, _("Link updated."))
    else:
        messages.error(request, _("That could not be saved — check the form."))

    return redirect("staff:seo_backlinks", slug=backlink.organization.slug)
