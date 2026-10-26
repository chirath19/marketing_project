"""The public contact and quote forms.

Open by design — they are how someone reaches the agency. Four defences
run on every submission: a honeypot, a signed render timestamp, a rate
limit by address, and content heuristics. Only the honeypot rejects
outright; everything else flags, because losing a real enquiry silently
is far worse than a staff member skimming past an advert.

Nothing is sent anywhere. The submission is written to PostgreSQL, a lead
is created or updated, and staff are notified in-app.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.ratelimit import RateLimit, check, client_ip, hash_key
from apps.leads import spam
from apps.leads.forms import ContactForm, QuoteRequestForm
from apps.leads.models import LeadSource, SubmissionKind
from apps.leads.services import record_submission

logger = logging.getLogger(__name__)

#: Generous enough that a person correcting a typo is never caught, tight
#: enough that a script is.
CONTACT_IP = RateLimit("contact:ip", limit=5, window=timedelta(hours=1))

#: Prompts beside the form. Interface guidance rather than marketing
#: copy, which is why it lives here and not in the CMS: it describes what
#: this particular form does with what you type into it.
HELPFUL_DETAILS = (
    "What the business does, and who buys from it",
    "Your website, if you have one",
    "What you have already tried, and how it went",
    "Which services you are considering, if you know",
    "Anything that makes this urgent or awkward",
)


def _submission_context(request: HttpRequest) -> dict:
    """Provenance kept with the submission.

    The address is hashed: this is a record of an enquiry, not a log of
    who browsed the site.
    """
    return {
        "ip_hash": hash_key(client_ip(request)),
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
        "page_url": request.POST.get("page_url", "")[:500] or request.path,
    }


def _submitter(request: HttpRequest) -> dict:
    """Who is sending this, if we already know.

    Anonymous visitors are the normal case and get an empty dict — the
    quote still works, it simply has no owner until somebody attaches it.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.is_staff_member:
        return {}

    from apps.organizations import selectors as organization_selectors

    return {
        "submitted_by": user,
        "organization": getattr(request, "organization", None)
        or organization_selectors.primary_organization_for(user),
    }


def _classify(form) -> spam.Verdict:  # noqa: ANN001
    return spam.classify(
        message=form.cleaned_data.get("message", ""),
        name=form.cleaned_data.get("name", ""),
        elapsed_seconds=form.elapsed_seconds,
    )


@require_http_methods(["GET", "POST"])
def contact_form(request: HttpRequest) -> HttpResponse:
    """The enquiry form, shown on its own page.

    On success the visitor is redirected rather than shown the response
    directly, so a refresh cannot resubmit the same enquiry.
    """
    throttled = False

    if request.method == "POST":
        verdict = check(CONTACT_IP, client_ip(request))
        if not verdict.allowed:
            throttled = True
            form = ContactForm(request.POST)
            form.add_error(
                None,
                (
                    "We have had several messages from this connection recently. "
                    "Please try again shortly, or email us directly."
                ),
            )
        else:
            form = ContactForm(request.POST)
            if form.is_valid():
                classification = _classify(form)
                record_submission(
                    kind=SubmissionKind.CONTACT,
                    source=LeadSource.CONTACT_FORM,
                    is_spam=classification.is_spam,
                    spam_reason=classification.reason,
                    **{
                        key: form.cleaned_data.get(key, "")
                        for key in (
                            "name",
                            "company",
                            "email",
                            "phone",
                            "website",
                            "subject",
                            "message",
                        )
                    },
                    **_submission_context(request),
                )
                return redirect("public:contact_sent")
    else:
        form = ContactForm()

    return render(
        request,
        "public/leads/contact.html",
        {
            "form": form,
            "throttled": throttled,
            "helpful_details": HELPFUL_DETAILS,
        },
        status=429 if throttled else 200,
    )


def contact_sent(request: HttpRequest) -> HttpResponse:
    """The success response.

    Says what will happen and when, and deliberately does not promise an
    automatic email — none is sent.
    """
    return render(request, "public/leads/sent.html")


@require_http_methods(["POST"])
def quote_submit(request: HttpRequest) -> HttpResponse:
    """Submit the quote selection built in the catalogue.

    The selected services are copied onto the submission with the prices
    as shown, so the request records what the visitor was quoted rather
    than whatever the catalogue says later.
    """
    from apps.catalog import quote_selection
    from apps.catalog.pricing import price_visible

    lines = quote_selection.lines(request)
    if request.operating.require_quote_account and request.GET.get("guest") != "1":
        return redirect("organizations:quote_create")
    verdict = check(CONTACT_IP, client_ip(request))
    form = QuoteRequestForm(request.POST)

    if not verdict.allowed:
        form.add_error(
            None,
            (
                "We have had several messages from this connection recently. "
                "Please try again shortly, or email us directly."
            ),
        )
    elif form.is_valid() and (lines or form.cleaned_data.get("message")):
        classification = _classify(form)

        submission = record_submission(
            kind=SubmissionKind.QUOTE_REQUEST,
            source=LeadSource.QUOTE_BUILDER,
            # A signed-in client's quote is attached to them and to their
            # organization at the moment it is created, so it appears in
            # their own workspace without anybody having to match it up
            # by email afterwards.
            **_submitter(request),
            subject=f"Quote request: {len(lines)} service{'s' if len(lines) != 1 else ''}",
            is_spam=classification.is_spam,
            spam_reason=classification.reason,
            quote_items=[
                {
                    "service": line.service,
                    "package": line.package,
                    "name": line.name,
                    "price_display": line.priced.price_display
                    if price_visible(line.priced, request.operating)
                    else "",
                    "billing_display": line.priced.billing_display
                    if price_visible(line.priced, request.operating)
                    else "",
                }
                for line in lines
            ],
            # The wording the visitor actually saw, not the key it was
            # stored under: a staff member reading the enquiry should not
            # have to decode "3k_7k".
            objective=form.objective_label(),
            budget_range=form.budget_label(),
            **{
                key: form.cleaned_data.get(key, "")
                for key in ("name", "company", "email", "phone", "website", "message")
            },
            **_submission_context(request),
        )

        request.session.pop("guest_quote_token", None)
        if not submission.is_spam and submission.quote_request.submitted_by_id is None:
            from apps.leads.guest import issue

            request.session["guest_quote_token"] = issue(submission.quote_request)
        quote_selection.clear(request)
        return redirect("public:quote_sent")

    # Re-render the quote page with the form's errors rather than losing
    # the selection the visitor built.
    from apps.catalog.views.public import quote_review

    if not lines and not form.errors and not form.cleaned_data.get("message"):
        form.add_error("message", "Describe your custom requirements or select a service.")
    request.quote_form = form
    return quote_review(request)


def quote_sent(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "public/leads/sent.html",
        {"is_quote": True, "guest_quote_token": request.session.get("guest_quote_token")},
    )
