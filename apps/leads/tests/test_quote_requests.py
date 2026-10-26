"""The quote request workflow.

Three things are worth protecting here and they are what most of these
tests are about: that a quote reaches staff without anything being
emailed, that its status machine refuses moves it should refuse, and —
above all — that one client can never see another's quote. The last is
the only record in this domain a client can open at all.
"""

from __future__ import annotations

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.leads import quote_services, selectors
from apps.leads.models import (
    QuoteActivity,
    QuoteRequestItem,
    QuoteStatus,
    SubmissionKind,
)
from apps.leads.tests.factories import make_quote_request
from apps.organizations.tests.factories import make_member, make_org
from apps.staff.tests.factories import (
    PASSWORD,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


def _client_in(organization, email: str):  # noqa: ANN001, ANN202
    """A client account that actively belongs to an organization.

    Membership is its own row rather than a column on the user, which is
    the whole point of the organizations domain — so a test fixture has
    to create it the same way the application does.
    """
    user = make_user(email=email)
    make_member(organization, user)
    return user


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def super_admin():
    return make_super_admin_user()


@pytest.fixture
def pricer():
    """Reads and works quotes, but cannot accept one on a client's behalf."""
    return make_staff_member(
        "pricer@heliograph.agency", has_all_client_access=True,
        roles=[make_role("Pricer", ["quotes_view", "quotes_edit"])],
    )


@pytest.fixture
def closer():
    """May also record a decision."""
    return make_staff_member(
        "closer@heliograph.agency", has_all_client_access=True,
        roles=[make_role("Closer", ["quotes_view", "quotes_edit",
                                    "quotes_approve", "quotes_assign"])],
    )


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_a_quote_submission_creates_a_quote_request():
    quote = make_quote_request(services=["Technical SEO audit",
                                         "Google Ads management"])

    assert quote.reference.startswith("QR-")
    assert quote.status == QuoteStatus.NEW
    assert quote.items.count() == 2
    assert quote.contact_email == "priya@vantage.example"


def test_the_contact_details_are_copied_not_referenced():
    """A quote has to say who it was for even after the lead is corrected."""
    quote = make_quote_request(name="Priya Raman")

    quote.lead.name = "Someone Else"
    quote.lead.save(update_fields=["name"])
    quote.refresh_from_db()

    assert quote.contact_name == "Priya Raman"


def test_nothing_is_emailed_when_a_quote_arrives():
    make_quote_request()

    assert mail.outbox == []


def test_a_quote_raises_an_in_app_notification_for_quote_holders():
    from apps.notifications.models import Notification

    staff = make_staff_member("pricer@heliograph.agency", has_all_client_access=True,
                              roles=[make_role("Pricer", ["quotes_view"])])
    make_staff_member("blogger@heliograph.agency",
                      roles=[make_role("Blogger", ["blog_view"])])

    quote = make_quote_request()
    recipients = set(
        Notification.objects.filter(category="quote").values_list(
            "recipient__email", flat=True)
    )

    assert staff.user.email in recipients
    assert "blogger@heliograph.agency" not in recipients
    assert Notification.objects.filter(
        category="quote", title__contains=quote.reference).exists()


def test_the_submission_still_lands_in_the_inbox():
    """The evidence is kept, and reachable, alongside the workflow record."""
    quote = make_quote_request()

    assert quote.submission is not None
    assert quote.submission.kind == SubmissionKind.QUOTE_REQUEST
    assert quote.submission.quote_items.count() == quote.items.count()


def test_references_are_unique_and_sequential():
    first = make_quote_request(email="one@example.com")
    second = make_quote_request(email="two@example.com")

    assert first.reference != second.reference
    assert int(second.reference.rsplit("-", 1)[1]) == \
        int(first.reference.rsplit("-", 1)[1]) + 1


def test_a_signed_in_client_is_attached_to_their_own_quote():
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")

    quote = make_quote_request(submitted_by=user, organization=org)

    assert quote.submitted_by == user
    assert quote.organization == org


# ---------------------------------------------------------------------------
# The status machine
# ---------------------------------------------------------------------------


def test_a_quote_moves_through_the_workflow(closer):
    quote = make_quote_request()

    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                 actor=closer.user)
    quote_services.change_status(quote=quote, status=QuoteStatus.PROPOSAL_READY,
                                 actor=closer.user)
    quote_services.change_status(quote=quote, status=QuoteStatus.ACCEPTED,
                                 actor=closer.user)

    quote.refresh_from_db()
    assert quote.status == QuoteStatus.ACCEPTED
    assert quote.decided_at is not None


def test_an_impossible_move_is_refused(closer):
    """A brand new request cannot be accepted: there is nothing to accept."""
    quote = make_quote_request()

    with pytest.raises(ValidationError):
        quote_services.change_status(quote=quote, status=QuoteStatus.ACCEPTED,
                                     actor=closer.user)

    quote.refresh_from_db()
    assert quote.status == QuoteStatus.NEW


def test_an_accepted_quote_cannot_be_un_accepted(closer):
    """The client agreed. Pretending otherwise loses the only record of it."""
    quote = make_quote_request()
    quote.status = QuoteStatus.ACCEPTED
    quote.save(update_fields=["status"])

    with pytest.raises(ValidationError):
        quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                     actor=closer.user)


def test_a_declined_quote_can_be_picked_back_up(closer):
    quote = make_quote_request()
    quote.status = QuoteStatus.DECLINED
    quote.save(update_fields=["status"])

    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                 actor=closer.user)

    quote.refresh_from_db()
    assert quote.status == QuoteStatus.REVIEWING


def test_pricing_a_quote_is_not_the_same_right_as_deciding_one(pricer):
    """Adjusting a price is day-to-day work. Recording a commitment is not."""
    quote = make_quote_request()
    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                 actor=pricer.user)
    quote_services.change_status(quote=quote, status=QuoteStatus.PROPOSAL_READY,
                                 actor=pricer.user)

    with pytest.raises(PermissionDenied):
        quote_services.change_status(quote=quote, status=QuoteStatus.ACCEPTED,
                                     actor=pricer.user)


def test_every_change_lands_on_the_timeline(closer):
    quote = make_quote_request()
    before = quote.activities.count()

    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                 actor=closer.user)
    quote_services.assign(quote=quote, assignee=closer.user, actor=closer.user)

    assert quote.activities.count() == before + 2


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def test_scope_can_be_adjusted_without_touching_the_submission(pricer):
    """The submission is the record of what was asked for."""
    from decimal import Decimal

    quote = make_quote_request()
    item = quote.items.first()
    original = quote.submission.quote_items.first()

    quote_services.update_scope(
        quote=quote, actor=pricer.user, summary="Two phases.",
        lines={item.pk: {"quoted_amount": Decimal("2500.00"),
                         "is_included": True, "note": "Larger site."}},
    )

    item.refresh_from_db()
    original.refresh_from_db()
    assert item.quoted_amount == Decimal("2500.00")
    assert original.price_display == "$1,500", "the evidence must not change"


def test_dropping_a_line_keeps_the_record_that_it_was_asked_for(pricer):
    quote = make_quote_request(services=["Technical SEO audit", "Local search"])
    dropped = quote.items.first()

    quote_services.update_scope(
        quote=quote, actor=pricer.user,
        lines={dropped.pk: {"is_included": False}},
    )

    quote.refresh_from_db()
    assert QuoteRequestItem.objects.filter(pk=dropped.pk).exists()
    assert dropped.pk not in {item.pk for item in quote.included_items}
    assert dropped.pk in {item.pk for item in quote.dropped_items}


def test_totals_separate_monthly_from_one_off(pricer):
    from decimal import Decimal

    quote = make_quote_request(services=["Retainer", "Audit"])
    monthly, one_off = quote.items.all()[0], quote.items.all()[1]

    quote_services.update_scope(quote=quote, actor=pricer.user, lines={
        monthly.pk: {"is_included": True},
        one_off.pk: {"is_included": True},
    })
    QuoteRequestItem.objects.filter(pk=monthly.pk).update(
        quoted_amount=Decimal("2400"), billing_type="monthly", currency="USD")
    QuoteRequestItem.objects.filter(pk=one_off.pk).update(
        quoted_amount=Decimal("1500"), billing_type="one_time", currency="USD")

    quote.refresh_from_db()
    totals = quote_services.totals_for(quote)

    assert totals["monthly"] == Decimal("2400")
    assert totals["one_time"] == Decimal("1500")


# ---------------------------------------------------------------------------
# Client isolation — the part that matters most
# ---------------------------------------------------------------------------


@pytest.fixture
def two_clients():
    """Two unrelated clients, each with a quote."""
    org_a, org_b = make_org("Vantage Interiors"), make_org("Northwind Supply")
    user_a = _client_in(org_a, "a@vantage.example")
    user_b = _client_in(org_b, "b@northwind.example")
    quote_a = make_quote_request(email="a@vantage.example",
                                 submitted_by=user_a, organization=org_a)
    quote_b = make_quote_request(email="b@northwind.example",
                                 submitted_by=user_b, organization=org_b)
    return (user_a, quote_a), (user_b, quote_b)


def test_a_client_sees_only_their_own_quotes(two_clients):
    (user_a, quote_a), (_user_b, quote_b) = two_clients

    visible = set(selectors.quotes_for_client(user_a).values_list("pk", flat=True))

    assert quote_a.pk in visible
    assert quote_b.pk not in visible


def test_another_clients_quote_is_a_404_not_a_403(client, two_clients):
    """Confirming it exists is itself information they should not get."""
    (user_a, _quote_a), (_user_b, quote_b) = two_clients
    sign_in(client, user_a)

    response = client.get(reverse("organizations:quote_detail", args=[quote_b.pk]))

    assert response.status_code == 404


def test_a_client_cannot_reply_on_someone_elses_quote(client, two_clients):
    (user_a, _quote_a), (_user_b, quote_b) = two_clients
    sign_in(client, user_a)

    response = client.post(
        reverse("organizations:quote_reply", args=[quote_b.pk]),
        {"body": "Trying to reach into another company's quote."},
    )

    assert response.status_code == 404
    assert not QuoteActivity.objects.filter(quote=quote_b,
                                            body__contains="Trying").exists()


def test_a_client_cannot_decide_someone_elses_quote(client, two_clients):
    (user_a, _quote_a), (_user_b, quote_b) = two_clients
    quote_b.status = QuoteStatus.PROPOSAL_READY
    quote_b.save(update_fields=["status"])
    sign_in(client, user_a)

    response = client.post(
        reverse("organizations:quote_decision", args=[quote_b.pk]),
        {"decision": "accept"},
    )

    quote_b.refresh_from_db()
    assert response.status_code == 404
    assert quote_b.status == QuoteStatus.PROPOSAL_READY


def test_an_anonymous_visitor_is_sent_to_sign_in(client):
    quote = make_quote_request()

    response = client.get(reverse("organizations:quote_detail", args=[quote.pk]))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_a_quote_sent_before_an_organization_existed_stays_visible(client):
    """A visitor who registers afterwards should not lose sight of it."""
    user = make_user(email="solo@example.com")
    quote = make_quote_request(email="solo@example.com", submitted_by=user)

    assert quote.organization is None
    assert quote.pk in set(
        selectors.quotes_for_client(user).values_list("pk", flat=True))


def test_attaching_a_quote_to_an_organization_shares_it_with_colleagues(pricer):
    org = make_org("Vantage Interiors")
    colleague = _client_in(org, "colleague@vantage.example")
    quote = make_quote_request()

    assert quote.pk not in set(
        selectors.quotes_for_client(colleague).values_list("pk", flat=True))

    quote_services.attach_to_organization(quote=quote, organization=org,
                                          actor=pricer.user)

    assert quote.pk in set(
        selectors.quotes_for_client(colleague).values_list("pk", flat=True))


# ---------------------------------------------------------------------------
# Internal notes never reach the client
# ---------------------------------------------------------------------------


def test_an_internal_note_is_never_shown_to_the_client(client, pricer):
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")
    quote = make_quote_request(submitted_by=user, organization=org)

    quote_services.add_note(quote=quote, actor=pricer.user,
                            body="Margin is thin on this one.")
    sign_in(client, user)

    body = client.get(reverse("organizations:quote_detail",
                              args=[quote.pk])).content

    assert b"Margin is thin" not in body


def test_a_note_can_be_shared_deliberately(client, pricer):
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")
    quote = make_quote_request(submitted_by=user, organization=org)

    quote_services.add_note(quote=quote, actor=pricer.user, is_internal=False,
                            body="We need your analytics access to price this.")
    sign_in(client, user)

    body = client.get(reverse("organizations:quote_detail",
                              args=[quote.pk])).content

    assert b"analytics access" in body


def test_the_scope_summary_is_withheld_until_the_proposal_is_ready(client, pricer):
    """A half-written note read mid-draft causes the conversation it was
    meant to prevent."""
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")
    quote = make_quote_request(submitted_by=user, organization=org)

    quote_services.update_scope(quote=quote, actor=pricer.user,
                                summary="Draft thinking, not final.")
    sign_in(client, user)
    body = client.get(reverse("organizations:quote_detail",
                              args=[quote.pk])).content

    assert b"Draft thinking" not in body


def test_the_summary_appears_once_the_proposal_is_ready(client, closer):
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")
    quote = make_quote_request(submitted_by=user, organization=org)

    quote_services.update_scope(quote=quote, actor=closer.user,
                                summary="Two phases over three months.")
    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                 actor=closer.user)
    quote_services.change_status(quote=quote, status=QuoteStatus.PROPOSAL_READY,
                                 actor=closer.user)
    sign_in(client, user)

    body = client.get(reverse("organizations:quote_detail",
                              args=[quote.pk])).content

    assert b"Two phases over three months" in body


# ---------------------------------------------------------------------------
# What the client can do
# ---------------------------------------------------------------------------


def test_a_client_can_accept_a_proposal(client, closer):
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")
    quote = make_quote_request(submitted_by=user, organization=org)
    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                 actor=closer.user)
    quote_services.change_status(quote=quote, status=QuoteStatus.PROPOSAL_READY,
                                 actor=closer.user)
    sign_in(client, user)

    client.post(reverse("organizations:quote_decision", args=[quote.pk]),
                {"decision": "accept", "note": "Start in March please."})
    quote.refresh_from_db()

    assert quote.status == QuoteStatus.ACCEPTED
    assert quote.decided_at is not None
    assert mail.outbox == [], "a decision is recorded in-app, not emailed"


def test_a_client_cannot_accept_a_quote_that_is_not_ready(client):
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")
    quote = make_quote_request(submitted_by=user, organization=org)
    sign_in(client, user)

    client.post(reverse("organizations:quote_decision", args=[quote.pk]),
                {"decision": "accept"})
    quote.refresh_from_db()

    assert quote.status == QuoteStatus.NEW


def test_a_client_reply_notifies_the_owner_and_nobody_else(client, closer):
    from apps.notifications.models import Notification

    other = make_staff_member("other@heliograph.agency",
                              roles=[make_role("Other", ["quotes_view"])])
    org = make_org("Vantage Interiors")
    user = _client_in(org, "priya@vantage.example")
    quote = make_quote_request(submitted_by=user, organization=org)
    quote_services.assign(quote=quote, assignee=closer.user, actor=closer.user)
    sign_in(client, user)

    client.post(reverse("organizations:quote_reply", args=[quote.pk]),
                {"body": "Can we add social media to this?"})

    replies = Notification.objects.filter(title__contains="replied")
    assert replies.filter(recipient=closer.user).exists()
    assert not replies.filter(recipient=other.user).exists()


# ---------------------------------------------------------------------------
# Staff authorisation
# ---------------------------------------------------------------------------


STAFF_URLS = ["staff:module_quotes"]


@pytest.mark.parametrize("url_name", STAFF_URLS)
def test_a_client_user_is_refused_the_staff_pipeline(client, url_name):
    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse(url_name)).status_code == 403


def test_staff_without_the_permission_are_refused(client):
    nobody = make_staff_member("nobody@heliograph.agency")
    sign_in(client, nobody.user)

    assert client.get(reverse("staff:module_quotes")).status_code == 403


def test_a_pricer_cannot_assign(client, pricer):
    """Handing out work is a different decision from doing it."""
    quote = make_quote_request()
    sign_in(client, pricer.user)

    response = client.post(reverse("staff:quote_assign", args=[quote.pk]),
                           {"assignee": pricer.user.pk})

    quote.refresh_from_db()
    assert response.status_code == 403
    assert quote.assigned_to is None


def test_the_pipeline_lists_quotes(client, super_admin):
    quote = make_quote_request()
    sign_in(client, super_admin)

    body = client.get(reverse("staff:module_quotes")).content

    assert quote.reference.encode() in body


def test_the_pipeline_can_be_filtered_by_status(client, super_admin, closer):
    open_quote = make_quote_request(email="open@example.com")
    ready = make_quote_request(email="ready@example.com")
    quote_services.change_status(quote=ready, status=QuoteStatus.REVIEWING,
                                 actor=closer.user)
    sign_in(client, super_admin)

    body = client.get(reverse("staff:module_quotes"),
                      {"status": QuoteStatus.REVIEWING}).content

    assert ready.reference.encode() in body
    assert open_quote.reference.encode() not in body


def test_the_staff_detail_page_shows_the_original_words(client, super_admin):
    quote = make_quote_request(message="We need help before our spring launch.")
    sign_in(client, super_admin)

    body = client.get(reverse("staff:quote_detail", args=[quote.pk])).content

    assert b"spring launch" in body
