"""The staff quote pipeline.

A quote request has a life of its own: it is priced, scoped, sent, and
then accepted or declined. That is why it has its own views rather than
sharing the lead pipeline's — a lead is a relationship, and the same
client can have three quotes open at three different stages.

Every route is guarded by its own permission. Changing scope is
`quotes_edit`; recording that a client committed is `quotes_approve`,
because agreeing a price is a different kind of act from adjusting one.
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.leads import quote_services, quote_thread, selectors
from apps.leads.forms import (
    QuoteAssignForm,
    QuoteNoteForm,
    QuoteOrganizationForm,
    QuoteScopeForm,
    QuoteStatusForm,
)
from apps.leads.models import QuoteStatus
from apps.permissions.guards import require_permission

PER_PAGE = 25

QUOTES_BREADCRUMB = [{"label": "Quote requests", "href": "/staff/quotes/"}]


#: Empty-state wording per view, so a reader is told why *this* list is
#: empty rather than handed one sentence that fits none of them.
EMPTY_STATES = {
    "": {
        "icon": "◈",
        "title": "No quote requests yet",
        "body": "A request arrives when somebody builds a selection in the "
                "public catalogue and sends it. Nothing is emailed out — "
                "this is where they land.",
    },
    "mine": {
        "icon": "◎",
        "title": "Nothing assigned to you",
        "body": "Quotes appear here once one is assigned to you. You are "
                "notified directly when a client replies on a quote you own.",
    },
    "none": {
        "icon": "✓",
        "title": "Every quote has an owner",
        "body": "Nothing is sitting unclaimed.",
    },
}


def _shell(title: str, subtitle: str = "", **extra) -> dict:
    return {"page_title": title, "page_subtitle": subtitle,
            "nav_key": "quotes", **extra}


@require_permission("quotes_view")
def quote_list(request: HttpRequest) -> HttpResponse:
    """The pipeline, filtered by status and owner."""
    status = request.GET.get("status", "")
    owner = request.GET.get("owner", "")
    search = (request.GET.get("q") or "").strip()

    quotes = selectors.quote_requests(
        request.user, status=status, owner=owner, search=search,
    )
    counts = selectors.quote_pipeline_counts(request.user)

    paginator = Paginator(quotes, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    querystring = "&".join(
        f"{key}={value}" for key, value in
        (("status", status), ("owner", owner), ("q", search)) if value
    )

    return render(request, "leads/admin/quote_list.html", _shell(
        "Quote requests",
        "Selections built in the public catalogue, and what has happened "
        "to each since.",
        page_obj=page_obj, quotes=page_obj.object_list,
        status=status, owner=owner, search=search, querystring=querystring,
        stages=[
            {"value": value,
             "label": _("Active") if value == QuoteStatus.ACCEPTED else label,
             "count": counts.get(value, 0)}
            for value, label in QuoteStatus.choices
        ],
        empty_state=EMPTY_STATES.get(owner if not status else "",
                                     EMPTY_STATES[""]),
        is_filtered=bool(status or owner or search),
        columns=[{"label": "Reference"}, {"label": "Client"},
                 {"label": "Status"}, {"label": "Owner"},
                 {"label": "Received"}],
    ))


def _quote_or_404(request: HttpRequest, pk: int):  # noqa: ANN202
    quote = selectors.get_quote_request(request.user, pk)
    if quote is None:
        raise Http404("No such quote request.")
    return quote


@require_permission("quotes_view")
def quote_detail(request: HttpRequest, pk: int, *, reply_error="", reply_body="",
                 reply_mode="reply") -> HttpResponse:
    """One quote: what was asked for, what is being quoted, and the
    whole timeline of how it got there."""
    quote = _quote_or_404(request, pk)
    thread = quote_thread.entries(quote, request.user)
    quote_services.mark_viewed(quote=quote, actor=request.user)
    quote_thread.mark_read(quote=quote, actor=request.user)

    return render(request, "leads/admin/quote_detail.html", _shell(
        quote.reference, f"{quote.contact_name}"
        + (f" · {quote.company_name}" if quote.company_name else ""),
        quote=quote,
        totals=quote_services.totals_for(quote),
        thread=thread,
        reply_error=reply_error, reply_body=reply_body, reply_mode=reply_mode,
        thread_client=quote_thread.thread_client(quote),
        services=quote.subscriptions.order_by("name"),
        status_form=QuoteStatusForm(quote=quote),
        assign_form=QuoteAssignForm(initial={"assignee": quote.assigned_to}),
        scope_form=QuoteScopeForm(initial={"summary": quote.staff_summary}),
        note_form=QuoteNoteForm(),
        organization_form=QuoteOrganizationForm(
            initial={"organization": quote.organization}),
        breadcrumbs=QUOTES_BREADCRUMB,
    ))


def _back(quote) -> HttpResponse:  # noqa: ANN001
    return redirect("staff:quote_detail", pk=quote.pk)


@require_permission("quotes_view")
@require_http_methods(["POST"])
def quote_status(request: HttpRequest, pk: int) -> HttpResponse:
    """Move the quote along.

    Guarded at `quotes_view` here and again, more strictly, in the
    service layer: accepting or declining needs `quotes_approve`, and
    deciding that in one place means the rule holds for every caller.
    """
    quote = _quote_or_404(request, pk)
    form = QuoteStatusForm(request.POST, quote=quote)

    if form.is_valid():
        try:
            quote_services.change_status(
                quote=quote, status=form.cleaned_data["status"],
                actor=request.user, note=form.cleaned_data.get("note", ""),
            )
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        except PermissionDenied:
            messages.error(request, _("You may not record that decision."))
        else:
            messages.success(request, _("Status updated."))
    else:
        messages.error(request, _("That is not a move this quote can make."))

    return _back(quote)


@require_permission("quotes_assign")
@require_http_methods(["POST"])
def quote_assign(request: HttpRequest, pk: int) -> HttpResponse:
    quote = _quote_or_404(request, pk)
    form = QuoteAssignForm(request.POST)

    if form.is_valid():
        quote_services.assign(quote=quote, assignee=form.cleaned_data["assignee"],
                              actor=request.user)
        messages.success(request, _("Owner updated."))

    return _back(quote)


@require_permission("quotes_edit")
@require_http_methods(["POST"])
def quote_note(request: HttpRequest, pk: int) -> HttpResponse:
    quote = _quote_or_404(request, pk)
    form = QuoteNoteForm(request.POST)

    if form.is_valid():
        quote_services.add_note(
            quote=quote, body=form.cleaned_data["body"], actor=request.user,
            is_internal=not form.cleaned_data.get("share_with_client"),
        )
        messages.success(
            request,
            _("Note added and shared with the client.")
            if form.cleaned_data.get("share_with_client")
            else _("Internal note added."),
        )
    else:
        messages.error(request, _("A note needs something in it."))

    return _back(quote)


@require_permission("quotes_edit")
@require_http_methods(["POST"])
def quote_reply(request: HttpRequest, pk: int) -> HttpResponse:
    """Post on the quote's conversation: a reply the client sees, or with
    `mode=note`, an internal note only staff see."""
    quote = _quote_or_404(request, pk)
    body = request.POST.get("body", "")
    internal = request.POST.get("mode") == "note"
    try:
        if len(body.strip()) > 5000:
            raise ValidationError("Write a message of 1–5,000 characters.")
        if internal:
            quote_services.add_note(quote=quote, body=body, actor=request.user)
        else:
            quote_thread.reply(quote=quote, actor=request.user, body=body)
    except ValidationError as exc:
        return quote_detail(request, pk, reply_error=exc.messages[0], reply_body=body,
                            reply_mode="note" if internal else "reply")
    else:
        messages.success(request, _("Internal note saved.") if internal
                         else _("Reply sent to the client."))
    return redirect(quote.get_absolute_url() + "#quote-conversation")


@require_permission("quotes_edit")
@require_http_methods(["POST"])
def quote_scope(request: HttpRequest, pk: int) -> HttpResponse:
    """Adjust what is being quoted.

    Line amounts, whether a line is in scope, and the summary the client
    eventually reads. The submission behind the quote is never touched —
    it is the record of what was asked for.
    """
    quote = _quote_or_404(request, pk)
    form = QuoteScopeForm(request.POST)

    lines: dict[int, dict] = {}
    for item in quote.items.all():
        values: dict = {
            "is_included": f"include-{item.pk}" in request.POST,
            "note": (request.POST.get(f"note-{item.pk}") or "").strip()[:250],
        }

        raw = (request.POST.get(f"amount-{item.pk}") or "").strip()
        if raw:
            from decimal import Decimal, InvalidOperation

            try:
                values["quoted_amount"] = Decimal(raw)
            except InvalidOperation:
                messages.error(
                    request,
                    _("“%(value)s” is not an amount, so %(line)s was left alone.")
                    % {"value": raw, "line": item.name},
                )
                continue
        else:
            # Cleared on purpose: this line is quoted on scope.
            values["quoted_amount"] = None

        lines[item.pk] = values

    try:
        quote_services.update_scope(
            quote=quote, actor=request.user,
            summary=form.cleaned_data.get("summary") if form.is_valid() else None,
            lines=lines,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, _("Scope saved."))
    return _back(quote)


@require_permission("quotes_edit")
@require_http_methods(["POST"])
def quote_organization(request: HttpRequest, pk: int) -> HttpResponse:
    quote = _quote_or_404(request, pk)
    form = QuoteOrganizationForm(request.POST)

    if form.is_valid():
        quote_services.attach_to_organization(
            quote=quote, organization=form.cleaned_data["organization"],
            actor=request.user,
        )
        messages.success(request, _("Client updated."))

    return _back(quote)


@require_permission('quotes_edit')
@require_http_methods(['POST'])
def quote_add_line(request, pk):
    from apps.leads.forms import QuoteLineForm
    quote = _quote_or_404(request, pk)
    form = QuoteLineForm(request.POST)
    if form.is_valid():
        try:
            quote_services.add_scope_line(actor=request.user, quote=quote, **form.cleaned_data)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(request, 'Proposal line added.')
    else:
        messages.error(request, 'Enter a name, non-negative amount and three-letter currency code.')
    return _back(quote)
