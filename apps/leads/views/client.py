"""A client's own quote requests, inside their workspace.

These views live in the domain that owns the data and are mounted under
the organizations namespace, which is where the client expects to find
them — the same arrangement the staff dashboard already uses for the
Inbox and the lead pipeline.

Every one of them resolves the quote through `selectors.client_quote`,
which applies the ownership rule to the row itself. A guessed id is
refused by the same check that filtered the list, not by the template.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.leads import policies, quote_services, quote_thread, selectors
from apps.leads.forms import ClientQuoteReplyForm
from apps.leads.models import QuoteStatus


@login_required
def quote_list(request: HttpRequest) -> HttpResponse:
    """Every quote this client may see."""
    if not request.user.is_client:
        raise Http404
    quotes = selectors.quotes_for_client(request.user).filter(
        Q(organization=request.organization) | Q(organization__isnull=True)
    )

    return render(
        request,
        "leads/client/quote_list.html",
        {
            "page_title": "Quotes",
            "portal_key": "quotes",
            "quotes": quotes,
            "awaiting_decision": [q for q in quotes if q.status == QuoteStatus.PROPOSAL_READY],
            "active_quotes": [q for q in quotes if q.is_active_work],
            "other_quotes": [q for q in quotes if not q.is_active_work],
        },
    )


def _quote_or_404(request: HttpRequest, pk: int):  # noqa: ANN202
    quote = selectors.client_quote(request.user, pk)
    if quote is None:
        # 404 rather than 403. Confirming that a quote exists is itself
        # information somebody else's client should not get.
        raise Http404("No such quote.")
    return quote


@login_required
def quote_detail(request: HttpRequest, pk: int, *, reply_error="", reply_body="",
                 reply_mode="reply") -> HttpResponse:
    quote = _quote_or_404(request, pk)
    thread = quote_thread.entries(quote, request.user)
    quote_services.mark_viewed(quote=quote, actor=request.user)
    quote_thread.mark_read(quote=quote, actor=request.user)

    return render(
        request,
        "leads/client/quote_detail.html",
        {
            "page_title": quote.reference,
            "portal_key": "quotes",
            "quote": quote,
            "items": quote.included_items,
            "totals": quote_services.totals_for(quote),
            # Filtered in the selector, not here: forgetting the condition in
            # one template is how an internal note reaches a client.
            "thread": thread,
            "services": quote.subscriptions.order_by("name") if quote.organization_id else [],
            "can_decide": quote.status == QuoteStatus.PROPOSAL_READY
            and policies.can_client_decide_quote(request.user, quote),
            "reply_form": ClientQuoteReplyForm(),
            "reply_error": reply_error, "reply_body": reply_body, "reply_mode": reply_mode,
        },
    )


@login_required
@require_http_methods(["POST"])
def quote_reply(request: HttpRequest, pk: int) -> HttpResponse:
    quote = _quote_or_404(request, pk)
    form = ClientQuoteReplyForm(request.POST)

    if form.is_valid():
        try:
            quote_services.client_reply(
                quote=quote, body=form.cleaned_data["body"], actor=request.user,
            )
        except ValidationError as exc:
            return quote_detail(request, pk, reply_error=exc.messages[0],
                                reply_body=request.POST.get("body", ""))
    else:
        return quote_detail(request, pk, reply_error=" ".join(form.errors["body"]),
                            reply_body=request.POST.get("body", ""))

    return redirect(quote.get_client_url() + "#quote-conversation")


@login_required
@require_http_methods(["POST"])
def quote_decision(request: HttpRequest, pk: int) -> HttpResponse:
    """The client accepting or declining their own proposal."""
    quote = _quote_or_404(request, pk)
    if request.POST.get("decision") not in {"accept", "decline"}:
        raise Http404
    accepted = request.POST.get("decision") == "accept"

    try:
        quote_services.client_decision(
            quote=quote,
            accepted=accepted,
            actor=request.user,
            note=(request.POST.get("note") or "").strip()[:250],
        )
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    except PermissionDenied:
        raise Http404("No such quote.") from None
    else:
        messages.success(
            request,
            _(
                "Thank you — we have recorded that you accepted this quote. "
                "Your account team will be in touch to start the work."
            )
            if accepted
            else _("Recorded. We have let your account team know."),
        )

    return redirect("organizations:quote_detail", pk=quote.pk)


@login_required
@require_http_methods(["GET", "POST"])
def quote_create(request):
    from datetime import timedelta

    from apps.catalog import quote_selection
    from apps.catalog.pricing import price_visible
    from apps.core.ratelimit import RateLimit, check
    from apps.leads.forms import ClientQuoteCreateForm
    from apps.leads.services import record_submission
    from apps.organizations.selectors import membership_for

    if not request.user.is_client:
        return render(request, "leads/client/quote_unavailable.html", {"staff_account": True})
    if not request.organization:
        return redirect("organizations:setup")
    if not membership_for(request.user, request.organization):
        raise Http404
    if request.organization.status != "active":
        return render(
            request,
            "leads/client/quote_unavailable.html",
            {"organization": request.organization},
        )
    lines = {line.service.pk: line for line in quote_selection.lines(request)}
    form = ClientQuoteCreateForm(
        request.POST if request.method == "POST" else None, initial={"services": list(lines)}
    )
    if request.method == "POST" and form.is_valid():
        limit = check(
            RateLimit("quote:client", limit=10, window=timedelta(hours=1)), str(request.user.pk)
        )
        if not limit.allowed:
            form.add_error(None, "You have sent several requests recently. Please try again later.")
        else:
            items = []
            for service in form.cleaned_data["services"]:
                line = lines.get(service.pk)
                priced = line.priced if line else service
                items.append(
                    {
                        "service": service,
                        "package": line.package if line else None,
                        "name": line.name if line else service.name,
                        "price_display": priced.price_display
                        if price_visible(priced, request.operating)
                        else "",
                        "billing_display": priced.billing_display
                        if price_visible(priced, request.operating)
                        else "",
                    }
                )
            submission = record_submission(
                name=request.user.get_full_name(),
                email=request.user.email,
                company=request.organization.name,
                message=form.cleaned_data["message"],
                kind="quote_request",
                source="quote_builder",
                subject="Client quotation request",
                submitted_by=request.user,
                organization=request.organization,
                quote_items=items,
            )
            quote_selection.clear(request)
            messages.success(
                request, "Your request is with the team. Replies and the proposal will appear here."
            )
            return redirect("organizations:quote_detail", pk=submission.quote_request.pk)
    return render(
        request,
        "leads/client/quote_create.html",
        {
            "form": form,
            "portal_key": "quotes",
            "selected_lines": list(lines.values()),
        },
    )
