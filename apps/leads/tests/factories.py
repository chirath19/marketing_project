"""Test helpers for leads and submissions."""

from __future__ import annotations

from apps.leads.models import (
    ContactSubmission,
    Lead,
    LeadSource,
    LeadStatus,
    SubmissionKind,
)

__all__ = ["make_lead", "make_submission", "make_quote_request",
           "CONTACT_POST"]

#: A valid public submission. The honeypot stays empty and the timestamp
#: is supplied by the form on render, so tests post without it — which
#: means "unknown", not "instant".
CONTACT_POST = {
    "name": "Priya Raman",
    "company": "Vantage Interiors",
    "email": "priya@vantage.example",
    "phone": "+94 11 234 5678",
    "website": "https://vantage.example",
    "subject": "Help with search and paid ads",
    "message": "We are launching a new range in spring and want to be visible "
               "for it. Can you help with search and paid ads?",
    "website_url": "",
}


def make_lead(name: str = "Priya Raman", *, email: str = "priya@vantage.example",
              status: str = LeadStatus.NEW, **fields) -> Lead:
    defaults = {"email": email, "status": status,
                "source": LeadSource.CONTACT_FORM}
    defaults.update(fields)
    return Lead.objects.create(name=name, **defaults)


def make_submission(*, name: str = "Priya Raman",
                    email: str = "priya@vantage.example",
                    message: str = "We would like some help with search.",
                    kind: str = SubmissionKind.CONTACT, **fields) -> ContactSubmission:
    return ContactSubmission.objects.create(
        name=name, email=email, message=message, kind=kind, **fields,
    )


def make_quote_request(*, name: str = "Priya Raman",
                       email: str = "priya@vantage.example",
                       organization=None, submitted_by=None,  # noqa: ANN001
                       services: list[str] | None = None,
                       **fields):  # noqa: ANN201
    """A quote request, built the way the real one is.

    Through the submission path rather than by creating the row
    directly, so a test exercises the same code a visitor does — a quote
    that exists but never went through `record_submission` would not have
    a reference, a timeline or a notification, and would quietly prove
    nothing.
    """
    from apps.leads.models import QuoteRequest
    from apps.leads.services import record_submission

    submission = record_submission(
        name=name, email=email,
        message=fields.pop("message", "Please price these up."),
        kind=SubmissionKind.QUOTE_REQUEST,
        source=LeadSource.QUOTE_BUILDER,
        submitted_by=submitted_by, organization=organization,
        quote_items=[
            {"name": label, "price_display": "$1,500",
             "billing_display": "one time"}
            for label in (services or ["Technical SEO audit"])
        ],
        **fields,
    )
    return QuoteRequest.objects.get(submission=submission)
