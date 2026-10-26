"""The staff Inbox, the lead pipeline, and the notification centre.

Every route is guarded. The Inbox and the pipeline are platform-wide
rather than client-scoped — an enquiry predates any client relationship,
so there is no organization to scope it to yet.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.leads import selectors, services
from apps.leads.forms import (
    LeadAssignForm,
    LeadDetailsForm,
    LeadNoteForm,
    LeadStatusForm,
)
from apps.leads.models import ContactSubmission, Lead, LeadStatus, SubmissionKind
from apps.permissions.guards import require_permission, require_staff_member

PER_PAGE = 25

INBOX_BREADCRUMB = [{"label": "Inbox", "href": "/staff/inbox/"}]
LEADS_BREADCRUMB = [{"label": "Leads", "href": "/staff/leads/"}]


def _shell(title: str, subtitle: str = "", nav_key: str = "inbox", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": nav_key, **extra}


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


#: Empty-state wording per Inbox view. "Archived" and "Spam" being
#: empty is good news; "All" being empty on a new install is not a
#: problem either, and neither should read like an error.
INBOX_EMPTY_STATES = {
    "": {
        "icon": "✉",
        "title": "No enquiries yet",
        "body": "Contact and quote forms on the public site deliver here. "
                "Nothing is emailed out — this is where submissions arrive.",
    },
    "unread": {
        "icon": "✓",
        "title": "Everything has been read",
        "body": "Nothing in the inbox is waiting to be opened.",
    },
    "mine": {
        "icon": "◎",
        "title": "Nothing assigned to you",
        "body": "Enquiries appear here once their lead is assigned to you. "
                "Check the All view to pick something up.",
    },
    "archived": {
        "icon": "□",
        "title": "Nothing archived",
        "body": "Enquiries you archive are kept here rather than deleted, "
                "so they can always be brought back.",
    },
    "spam": {
        "icon": "⚠",
        "title": "Nothing flagged as spam",
        "body": "Suspected spam is stored and hidden rather than discarded. "
                "Marking something “Not spam” creates the lead it never got.",
    },
}


def _inbox_view(request: HttpRequest, *, kind: str, nav_key: str,
                title: str, subtitle: str) -> HttpResponse:
    view = request.GET.get("view", "")
    search = (request.GET.get("q") or "").strip()

    submissions = selectors.inbox(
        request.user, kind=kind,
        unread_only=view == "unread",
        archived=view == "archived",
        spam=view == "spam",
        mine=view == "mine",
        search=search,
    )

    paginator = Paginator(submissions, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    querystring = "&".join(
        f"{key}={value}" for key, value in (("view", view), ("q", search)) if value
    )

    return render(request, "leads/admin/inbox.html", _shell(
        title, subtitle, nav_key,
        page_obj=page_obj, submissions=page_obj.object_list,
        view=view, search=search, querystring=querystring,
        unread_total=selectors.unread_count(request.user),
        kind=kind,
        views=[("", "All"), ("unread", "Unread"), ("mine", "Assigned to me"),
               ("archived", "Archived"), ("spam", "Spam")],
        # What to say when a view is empty. Keyed by view so the reader
        # is told why *this* list is empty rather than being handed one
        # generic sentence that fits none of them.
        empty_state=INBOX_EMPTY_STATES.get(view, INBOX_EMPTY_STATES[""]),
        columns=[{"label": "From"}, {"label": "Subject"}, {"label": "Received"},
                 {"label": "", "align": "right", "sr_label": "Actions"}],
    ))


@require_permission("leads_view")
def inbox(request: HttpRequest) -> HttpResponse:
    """Every inbound submission. Where enquiries land, since nothing is
    emailed anywhere."""
    return _inbox_view(
        request, kind="", nav_key="inbox",
        title="Inbox",
        subtitle="Every enquiry and quote request. Nothing is emailed — this "
                 "is where they arrive.",
    )


@require_permission("quotes_view")
def quote_inbox(request: HttpRequest) -> HttpResponse:
    return _inbox_view(
        request, kind=SubmissionKind.QUOTE_REQUEST, nav_key="quotes",
        title="Quote requests",
        subtitle="Selections built from the service catalogue.",
    )


@require_permission("leads_view")
def inbox_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """One submission, with its lead alongside.

    Opening it marks it read — which is what opening something means.
    """
    submission = selectors.get_submission(request.user, pk)
    if submission is None:
        raise Http404

    services.mark_read(submission=submission, actor=request.user)

    return render(request, "leads/admin/submission.html", _shell(
        submission.display_subject, f"From {submission.name}",
        "inbox",
        submission=submission,
        lead=submission.lead,
        quote_items=submission.quote_items.all(),
        breadcrumbs=INBOX_BREADCRUMB,
    ))


@require_permission("leads_view")
@require_http_methods(["POST"])
def inbox_read(request: HttpRequest, pk: int) -> HttpResponse:
    submission = get_object_or_404(ContactSubmission, pk=pk)

    if request.POST.get("read") == "1":
        services.mark_read(submission=submission, actor=request.user)
    else:
        services.mark_unread(submission=submission, actor=request.user)

    return redirect(request.POST.get("next") or "staff:module_inbox")


@require_permission("leads_edit")
@require_http_methods(["POST"])
def inbox_archive(request: HttpRequest, pk: int) -> HttpResponse:
    submission = get_object_or_404(ContactSubmission, pk=pk)
    archived = request.POST.get("archived") == "1"

    services.set_archived(submission=submission, actor=request.user,
                          archived=archived)
    messages.success(request, _("Archived.") if archived else _("Restored."))
    return redirect(request.POST.get("next") or "staff:module_inbox")


@require_permission("leads_edit")
@require_http_methods(["POST"])
def inbox_spam(request: HttpRequest, pk: int) -> HttpResponse:
    submission = get_object_or_404(ContactSubmission, pk=pk)
    is_spam = request.POST.get("spam") == "1"

    services.set_spam(submission=submission, actor=request.user, is_spam=is_spam)
    messages.success(request, _("Marked as spam.") if is_spam
                     else _("Rescued. A lead has been created."))
    return redirect(request.POST.get("next") or "staff:module_inbox")


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


@require_permission("leads_view")
def lead_list(request: HttpRequest) -> HttpResponse:
    status = request.GET.get("status", "")
    owner = request.GET.get("owner", "")
    search = (request.GET.get("q") or "").strip()

    leads = selectors.visible_leads(request.user)

    if status in LeadStatus.values:
        leads = leads.filter(status=status)
    if owner == "unassigned":
        leads = leads.filter(assigned_to__isnull=True)
    elif owner == "mine":
        leads = leads.filter(assigned_to=request.user)
    if search:
        from django.db.models import Q

        leads = leads.filter(
            Q(name__icontains=search) | Q(email__icontains=search)
            | Q(company__icontains=search)
        )

    paginator = Paginator(leads, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    querystring = "&".join(
        f"{key}={value}" for key, value in
        (("status", status), ("owner", owner), ("q", search)) if value
    )

    return render(request, "leads/admin/list.html", _shell(
        "Leads", "The pipeline, newest activity first.", "leads",
        page_obj=page_obj, leads=page_obj.object_list,
        pipeline=selectors.pipeline_counts(request.user),
        status=status, owner=owner, search=search, querystring=querystring,
        columns=[{"label": "Lead"}, {"label": "Status"}, {"label": "Owner"},
                 {"label": "Last activity"},
                 {"label": "", "align": "right", "sr_label": "Actions"}],
    ))


@require_permission("leads_view")
def lead_detail(request: HttpRequest, pk: int) -> HttpResponse:
    lead = selectors.get_lead(request.user, pk)
    if lead is None:
        raise Http404

    return render(request, "leads/admin/detail.html", _shell(
        str(lead), lead.email, "leads",
        lead=lead,
        activities=lead.activities.all()[:50],
        submissions=lead.submissions.all(),
        note_form=LeadNoteForm(),
        status_form=LeadStatusForm(initial={"status": lead.status}),
        assign_form=LeadAssignForm(initial={"assignee": lead.assigned_to}),
        details_form=LeadDetailsForm.for_lead(lead),
        can_edit=request.user.has_perm("permissions.leads_edit"),
        can_assign=request.user.has_perm("permissions.leads_assign"),
        breadcrumbs=LEADS_BREADCRUMB,
    ))


@require_permission("leads_edit")
@require_http_methods(["POST"])
def lead_note(request: HttpRequest, pk: int) -> HttpResponse:
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadNoteForm(request.POST)

    if form.is_valid():
        services.add_note(lead=lead, actor=request.user,
                          body=form.cleaned_data["body"])
        messages.success(request, _("Note added."))
    else:
        messages.error(request, _("A note needs something in it."))

    return redirect("staff:lead_detail", pk=lead.pk)


@require_permission("leads_edit")
@require_http_methods(["POST"])
def lead_status(request: HttpRequest, pk: int) -> HttpResponse:
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadStatusForm(request.POST)

    if form.is_valid():
        try:
            services.change_status(lead=lead, new_status=form.cleaned_data["status"],
                                   actor=request.user,
                                   note=form.cleaned_data.get("note", ""))
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Status updated."))

    return redirect("staff:lead_detail", pk=lead.pk)


@require_permission("leads_assign")
@require_http_methods(["POST"])
def lead_assign(request: HttpRequest, pk: int) -> HttpResponse:
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadAssignForm(request.POST)

    if form.is_valid():
        try:
            services.assign(lead=lead, assignee=form.cleaned_data["assignee"],
                            actor=request.user)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(request, _("Assignment updated."))

    return redirect("staff:lead_detail", pk=lead.pk)


@require_permission("leads_edit")
@require_http_methods(["POST"])
def lead_details(request: HttpRequest, pk: int) -> HttpResponse:
    """Correct the agency's working copy.

    The submission itself is never touched — it is the record of what was
    actually sent.
    """
    lead = get_object_or_404(Lead, pk=pk)
    form = LeadDetailsForm(request.POST)

    if form.is_valid():
        for field, value in form.cleaned_data.items():
            setattr(lead, field, value if value is not None else "")
        lead.save()
        messages.success(request, _("Lead updated."))
    else:
        messages.error(request, _("Those details could not be saved."))

    return redirect("staff:lead_detail", pk=lead.pk)


# ---------------------------------------------------------------------------
# Notification centre
# ---------------------------------------------------------------------------


@require_staff_member
def notifications(request: HttpRequest) -> HttpResponse:
    """A person's own notifications, and nobody else's."""
    from apps.notifications import selectors as notification_selectors

    items = notification_selectors.for_user(request.user)
    paginator = Paginator(items, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    return render(request, "leads/admin/notifications.html", _shell(
        "Notifications", "What needs your attention.", "notifications",
        page_obj=page_obj, notifications=page_obj.object_list,
    ))


@require_staff_member
@require_http_methods(["POST"])
def notifications_read(request: HttpRequest) -> HttpResponse:
    from apps.notifications.services import mark_all_read

    mark_all_read(user=request.user)
    messages.success(request, _("All caught up."))
    return redirect("staff:module_notifications")


@require_staff_member
def notification_open(request: HttpRequest, pk: int) -> HttpResponse:
    """Open a notification and go where it points.

    Scoped to the signed-in user, so an id belonging to someone else is
    simply not found.
    """
    from apps.notifications import selectors as notification_selectors

    notification = notification_selectors.get_for_user(request.user, pk)
    if notification is None:
        raise Http404
    notification.mark_read()

    return redirect(notification.url or "staff:module_notifications")
