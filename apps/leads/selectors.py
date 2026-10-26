"""Read access for leads and the Inbox."""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.leads import policies
from apps.leads.models import ContactSubmission, Lead, LeadStatus, SubmissionKind


def visible_leads(actor) -> QuerySet:  # noqa: ANN001
    return Lead.objects.readable_by(actor).for_listing()


def get_lead(actor, pk: int):  # noqa: ANN001, ANN201
    return (
        visible_leads(actor)
        .prefetch_related("activities__actor", "submissions")
        .filter(pk=pk)
        .first()
    )


def inbox(actor, *, kind: str = "", unread_only: bool = False,
          archived: bool = False, spam: bool = False, mine: bool = False,
          search: str = "") -> QuerySet:  # noqa: ANN001
    """The Inbox, as the actor is allowed to see it.

    Spam and archived are opt-in rather than filtered out in the
    template, so the default list is the work that needs doing.

    `mine` follows the submission's lead to its owner: a submission has
    no assignee of its own, because the person is assigned to the
    relationship rather than to one message within it.
    """
    if not policies.can_view_leads(actor):
        return ContactSubmission.objects.none()

    queryset = ContactSubmission.objects.for_listing()

    queryset = queryset.filter(is_spam=spam)
    if not spam:
        queryset = queryset.filter(is_archived=archived)

    if kind in SubmissionKind.values:
        queryset = queryset.filter(kind=kind)

    if unread_only:
        queryset = queryset.filter(read_at__isnull=True)

    if mine:
        queryset = queryset.filter(lead__assigned_to=actor)

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(email__icontains=search)
            | Q(company__icontains=search) | Q(subject__icontains=search)
            | Q(message__icontains=search)
        )

    return queryset


def get_submission(actor, pk: int):  # noqa: ANN001, ANN201
    if not policies.can_view_leads(actor):
        return None

    return (
        ContactSubmission.objects
        .select_related("lead", "lead__assigned_to", "read_by")
        .prefetch_related("quote_items")
        .filter(pk=pk)
        .first()
    )


# ---------------------------------------------------------------------------
# Dashboard metrics
# ---------------------------------------------------------------------------


def inbox_counts(actor) -> dict:  # noqa: ANN001
    """The three numbers the dashboard shows, in one query.

    Aggregated rather than counted separately: this runs on the dashboard
    home, and three round trips for three numbers on the same table is
    two too many.
    """
    if not policies.can_view_leads(actor):
        return {"unread": 0, "new_leads": 0, "unassigned": 0}

    submissions = ContactSubmission.objects.filter(is_spam=False).aggregate(
        unread=Count("pk", filter=Q(read_at__isnull=True, is_archived=False)),
    )
    leads = Lead.objects.aggregate(
        new_leads=Count("pk", filter=Q(status=LeadStatus.NEW)),
        unassigned=Count("pk", filter=Q(
            assigned_to__isnull=True,
            status__in=[LeadStatus.NEW, LeadStatus.CONTACTED,
                        LeadStatus.QUALIFIED, LeadStatus.PROPOSAL],
        )),
    )

    return {**submissions, **leads}


def open_quote_count(actor) -> int:  # noqa: ANN001
    """Quote requests nobody has opened yet.

    Guarded by the quotes permission rather than the leads one: being
    allowed to see the pipeline is not the same as being allowed to see
    what people have asked to be priced.
    """
    if not policies.can_view_quotes(actor):
        return 0

    return (
        ContactSubmission.objects
        .filter(kind=SubmissionKind.QUOTE_REQUEST, is_spam=False,
                is_archived=False, read_at__isnull=True)
        .count()
    )


def unread_count(actor) -> int:  # noqa: ANN001
    """The Inbox badge."""
    if not policies.can_view_leads(actor):
        return 0
    return ContactSubmission.objects.unread().count()


def pipeline_counts(actor) -> list[dict]:  # noqa: ANN001
    """How many leads sit at each stage, for the pipeline tabs."""
    if not policies.can_view_leads(actor):
        return []

    counts = dict(
        Lead.objects.values_list("status").annotate(total=Count("pk"))
    )
    return [
        {"value": value, "label": label, "count": counts.get(value, 0)}
        for value, label in LeadStatus.choices
    ]


# ---------------------------------------------------------------------------
# Quote requests
# ---------------------------------------------------------------------------


def quote_requests(actor, *, status: str = "", owner: str = "",  # noqa: ANN001
                   search: str = "") -> QuerySet:
    """The quote pipeline, as this actor may see it."""
    from apps.leads.models import QuoteRequest

    if not policies.can_view_quotes(actor):
        return QuoteRequest.objects.none()

    queryset = _scoped_quotes(QuoteRequest.objects.for_listing(), actor)

    if status:
        queryset = queryset.filter(status=status)

    if owner == "me":
        queryset = queryset.filter(assigned_to=actor)
    elif owner == "none":
        queryset = queryset.filter(assigned_to__isnull=True)

    if search:
        queryset = queryset.filter(
            Q(reference__icontains=search) | Q(contact_name__icontains=search)
            | Q(contact_email__icontains=search)
            | Q(company_name__icontains=search)
        )

    return queryset


def get_quote_request(actor, pk: int):  # noqa: ANN001, ANN201
    """One quote, for staff.

    Read through the same permission the list uses, so a guessed id is
    refused by the rule that hid it rather than by the template.
    """
    from apps.leads.models import QuoteRequest

    if not policies.can_view_quotes(actor):
        return None

    return (
        _scoped_quotes(QuoteRequest.objects.all(), actor)
        .select_related("assigned_to", "organization", "lead", "submission",
                        "submitted_by")
        .prefetch_related("items__service", "activities__actor")
        .filter(pk=pk)
        .first()
    )


def quote_pipeline_counts(actor) -> dict:  # noqa: ANN001
    """One row per status, for the filter bar.

    A single grouped query rather than one count per status: there are
    seven of them, and seven round trips to draw a filter bar is six too
    many.
    """
    from apps.leads.models import QuoteRequest, QuoteStatus

    if not policies.can_view_quotes(actor):
        return {}

    counts = dict(
        _scoped_quotes(QuoteRequest.objects.all(), actor).values_list("status")
        .annotate(total=Count("pk"))
        .values_list("status", "total")
    )
    return {status: counts.get(status, 0) for status in QuoteStatus.values}


def open_quote_request_count(actor) -> int:  # noqa: ANN001
    """Quotes still waiting on somebody. For the dashboard tile."""
    from apps.leads.models import QuoteRequest

    if not policies.can_view_quotes(actor):
        return 0
    return QuoteRequest.objects.open().count()


# --- what a client sees ------------------------------------------------------


def quotes_for_client(user) -> QuerySet:  # noqa: ANN001
    """This client's own quote requests.

    Scoped by the model's own `readable_by`, which is the single place
    that rule lives — a list that filtered by hand would be one more
    thing to get wrong.
    """
    from apps.leads.models import QuoteRequest

    return (
        QuoteRequest.objects.readable_by(user)
        .select_related("assigned_to")
        .prefetch_related("items")
        .order_by("-created_at", "-pk")
    )


def client_quote(user, pk: int):  # noqa: ANN001, ANN201
    """One quote a client is entitled to open, or None."""
    from apps.leads.models import QuoteRequest

    quote = (
        QuoteRequest.objects
        .select_related("assigned_to", "organization")
        .prefetch_related("items", "activities__actor")
        .filter(pk=pk)
        .first()
    )
    if quote is None or not policies.can_client_see_quote(user, quote):
        return None
    return quote


def client_visible_activities(quote) -> list:  # noqa: ANN001
    """The timeline entries a client may read.

    Filtered in Python over an already-prefetched relation rather than
    with a second query, and filtered *here* rather than in the template
    so that forgetting the condition in one template cannot leak an
    internal note.
    """
    return [entry for entry in quote.activities.all() if not entry.is_internal]


def _scoped_quotes(queryset, actor):
    from apps.permissions.access import accessible_organization_ids
    ids = accessible_organization_ids(actor)
    if ids is None:
        return queryset
    return queryset.filter(Q(organization_id__in=ids) | Q(organization__isnull=True))
