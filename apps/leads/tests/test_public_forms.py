"""The public contact and quote forms.

Everything is stored; nothing is sent. The outbound-silence assertions
are the point of several of these.
"""

import pytest
from django.core import mail
from django.urls import reverse

from apps.leads.models import (
    ContactSubmission,
    Lead,
    LeadSource,
    LeadStatus,
    SubmissionKind,
)
from apps.leads.tests.factories import CONTACT_POST, make_lead

pytestmark = pytest.mark.django_db


# --- the happy path -----------------------------------------------------------


def test_the_contact_form_renders(client):
    response = client.get(reverse("public:contact_form"))

    assert response.status_code == 200
    assert b"What are you trying to achieve" in response.content


def test_the_contact_page_carries_the_form(client):
    """The CMS contact page has a contact_form section."""
    response = client.get("/contact/")

    assert response.status_code == 200
    assert b"Send us an enquiry" in response.content
    assert b'name="message"' in response.content


def test_a_submission_is_stored(client):
    client.post(reverse("public:contact_form"), CONTACT_POST)

    submission = ContactSubmission.objects.get()
    assert submission.email == "priya@vantage.example"
    assert submission.company == "Vantage Interiors"
    assert submission.kind == SubmissionKind.CONTACT
    assert submission.source == LeadSource.CONTACT_FORM


def test_a_submission_creates_a_lead(client):
    client.post(reverse("public:contact_form"), CONTACT_POST)

    lead = Lead.objects.get()
    assert lead.email == "priya@vantage.example"
    assert lead.status == LeadStatus.NEW
    assert lead.assigned_to is None


def test_a_submission_is_attached_to_its_lead(client):
    client.post(reverse("public:contact_form"), CONTACT_POST)

    submission = ContactSubmission.objects.get()
    assert submission.lead_id == Lead.objects.get().pk


def test_the_visitor_sees_a_success_response(client):
    response = client.post(reverse("public:contact_form"), CONTACT_POST,
                           follow=True)

    assert response.status_code == 200
    assert b"Thank you" in response.content


def test_success_redirects_so_a_refresh_cannot_resubmit(client):
    response = client.post(reverse("public:contact_form"), CONTACT_POST)

    assert response.status_code == 302
    assert response.url == reverse("public:contact_sent")


def test_the_success_page_does_not_promise_an_email(client):
    """Nothing is sent, so telling someone to watch their inbox would
    leave them waiting for something that never arrives."""
    body = client.get(reverse("public:contact_sent")).content.decode().lower()

    assert "check your inbox" not in body
    assert "confirmation email" not in body
    assert "we have sent" not in body


# --- nothing is sent -----------------------------------------------------------


def test_submitting_sends_no_email(client):
    """The platform sends nothing outbound. The locmem backend would
    capture anything that tried."""
    client.post(reverse("public:contact_form"), CONTACT_POST)

    assert mail.outbox == []


def test_submitting_creates_an_in_app_notification_instead(client):
    from apps.notifications.models import Notification
    from apps.staff.tests.factories import make_role, make_staff_member

    staff = make_staff_member("ops@heliograph.agency",
                              roles=[make_role("Leads", ["leads_view"])])

    client.post(reverse("public:contact_form"), CONTACT_POST)

    notification = Notification.objects.get(recipient=staff.user)
    assert "Priya Raman" in notification.title
    assert notification.url.endswith("/")
    assert not notification.is_read


def test_only_staff_who_can_see_leads_are_notified(client):
    from apps.notifications.models import Notification
    from apps.staff.tests.factories import make_role, make_staff_member

    allowed = make_staff_member("ops@heliograph.agency",
                                roles=[make_role("Leads", ["leads_view"])])
    other = make_staff_member("seo@heliograph.agency",
                              roles=[make_role("SEO only", ["seo_view"])])

    client.post(reverse("public:contact_form"), CONTACT_POST)

    assert Notification.objects.filter(recipient=allowed.user).exists()
    assert not Notification.objects.filter(recipient=other.user).exists()


def test_a_suspended_staff_member_is_not_notified(client):
    from apps.accounts.models import AccountStatus
    from apps.notifications.models import Notification
    from apps.staff.tests.factories import make_role, make_staff_member

    staff = make_staff_member("ops@heliograph.agency",
                              roles=[make_role("Leads", ["leads_view"])],
                              status=AccountStatus.SUSPENDED)

    client.post(reverse("public:contact_form"), CONTACT_POST)

    assert not Notification.objects.filter(recipient=staff.user).exists()


# --- repeat enquiries -----------------------------------------------------------


def test_a_second_enquiry_joins_the_existing_lead(client):
    """Otherwise somebody has to merge duplicates by hand later."""
    client.post(reverse("public:contact_form"), CONTACT_POST)
    client.post(reverse("public:contact_form"),
                {**CONTACT_POST, "message": "Following up on my last message."})

    assert Lead.objects.count() == 1
    assert ContactSubmission.objects.count() == 2


def test_a_second_enquiry_matches_on_a_differently_cased_email(client):
    client.post(reverse("public:contact_form"), CONTACT_POST)
    client.post(reverse("public:contact_form"),
                {**CONTACT_POST, "email": "PRIYA@Vantage.Example",
                 "message": "Another message from the same person."})

    assert Lead.objects.count() == 1


def test_an_enquiry_reopens_a_lost_lead(client):
    """A closed lead that is still receiving mail is not closed."""
    make_lead(status=LeadStatus.LOST)

    client.post(reverse("public:contact_form"), CONTACT_POST)

    lead = Lead.objects.get()
    assert lead.status == LeadStatus.CONTACTED
    assert lead.activities.filter(body__icontains="Reopened").exists()


def test_a_repeat_enquiry_fills_in_what_was_missing(client):
    make_lead(company="", phone="")

    client.post(reverse("public:contact_form"), CONTACT_POST)

    lead = Lead.objects.get()
    assert lead.company == "Vantage Interiors"
    assert lead.phone == "+94 11 234 5678"


# --- validation ------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["name", "email", "message"])
def test_required_fields_are_required(client, missing):
    client.post(reverse("public:contact_form"), {**CONTACT_POST, missing: ""})

    assert ContactSubmission.objects.count() == 0


def test_an_invalid_email_is_rejected(client):
    client.post(reverse("public:contact_form"),
                {**CONTACT_POST, "email": "not-an-email"})

    assert ContactSubmission.objects.count() == 0


def test_a_very_short_message_asks_for_more(client):
    response = client.post(reverse("public:contact_form"),
                           {**CONTACT_POST, "message": "hi"})

    assert ContactSubmission.objects.count() == 0
    assert b"a little more" in response.content


def test_the_email_is_normalised(client):
    client.post(reverse("public:contact_form"),
                {**CONTACT_POST, "email": "  Priya@Vantage.Example  "})

    assert ContactSubmission.objects.get().email == "priya@vantage.example"


# --- spam and rate limiting -------------------------------------------------------


def test_a_filled_honeypot_is_rejected_outright(client):
    """The one check that rejects rather than flags: a person cannot trip
    it by accident."""
    client.post(reverse("public:contact_form"),
                {**CONTACT_POST, "website_url": "http://spam.example"})

    assert ContactSubmission.objects.count() == 0


def test_the_honeypot_message_does_not_explain_the_trap(client):
    response = client.post(reverse("public:contact_form"),
                           {**CONTACT_POST, "website_url": "spam"})

    assert b"honeypot" not in response.content.lower()


def test_the_honeypot_field_actually_exists_on_the_form(client):
    """It was declared on a plain mixin once, which meant Django never
    collected it and the trap was not there at all."""
    from apps.leads.forms import ContactForm

    assert "website_url" in ContactForm().fields
    assert "rendered_at" in ContactForm().fields


def test_a_message_full_of_links_is_flagged_but_still_stored(client):
    """Flagging rather than rejecting: losing a real enquiry silently is
    far worse than a staff member skimming past an advert."""
    client.post(reverse("public:contact_form"), {
        **CONTACT_POST,
        "message": "Visit https://a.example https://b.example https://c.example "
                   "https://d.example for cheap services right now.",
    })

    submission = ContactSubmission.objects.get()
    assert submission.is_spam
    assert "links" in submission.spam_reason


def test_a_flagged_submission_creates_no_lead_and_no_notification(client):
    from apps.notifications.models import Notification
    from apps.staff.tests.factories import make_role, make_staff_member

    make_staff_member("ops@heliograph.agency",
                      roles=[make_role("Leads", ["leads_view"])])

    client.post(reverse("public:contact_form"), {
        **CONTACT_POST, "message": "buy backlinks cheap, best price guaranteed",
    })

    assert ContactSubmission.objects.get().is_spam
    assert Lead.objects.count() == 0
    assert Notification.objects.count() == 0


def test_a_flagged_submission_still_shows_the_visitor_success(client):
    """Telling a false positive they were rejected is how a real enquiry
    gets lost."""
    response = client.post(reverse("public:contact_form"), {
        **CONTACT_POST, "message": "buy backlinks cheap, best price guaranteed",
    })

    assert response.status_code == 302
    assert response.url == reverse("public:contact_sent")


def test_the_form_is_rate_limited(client):
    for index in range(5):
        client.post(reverse("public:contact_form"),
                    {**CONTACT_POST, "email": f"person{index}@example.com"})

    response = client.post(reverse("public:contact_form"),
                           {**CONTACT_POST, "email": "sixth@example.com"})

    assert response.status_code == 429
    assert not ContactSubmission.objects.filter(email="sixth@example.com").exists()


def test_a_submission_records_a_hashed_address_not_a_raw_one(client):
    """A record of an enquiry, not a log of who browsed."""
    client.post(reverse("public:contact_form"), CONTACT_POST)

    submission = ContactSubmission.objects.get()
    assert submission.ip_hash
    assert "127.0.0.1" not in submission.ip_hash
    assert len(submission.ip_hash) == 64


# --- quote requests ----------------------------------------------------------------


def test_a_quote_request_stores_what_was_selected(client):
    from apps.catalog.tests.factories import make_service

    service = make_service("SEO retainer", price="2400")
    client.post(reverse("public:quote_add"), {"service": service.pk})

    client.post(reverse("public:quote_submit"), CONTACT_POST)

    submission = ContactSubmission.objects.get()
    assert submission.kind == SubmissionKind.QUOTE_REQUEST
    assert submission.source == LeadSource.QUOTE_BUILDER

    item = submission.quote_items.get()
    assert item.name == "SEO retainer"
    assert item.price_display == "$2,400"


def test_a_quote_item_keeps_the_price_that_was_shown(client):
    """A quote has to record what the visitor was quoted, not whatever
    the catalogue says next week."""
    from decimal import Decimal

    from apps.catalog.tests.factories import make_service

    service = make_service("SEO retainer", price="2400")
    client.post(reverse("public:quote_add"), {"service": service.pk})
    client.post(reverse("public:quote_submit"), CONTACT_POST)

    service.price = Decimal("9999")
    service.save(update_fields=["price"])

    assert ContactSubmission.objects.get().quote_items.get().price_display == "$2,400"


def test_submitting_a_quote_clears_the_selection(client):
    from apps.catalog.tests.factories import make_service

    service = make_service("SEO retainer", price="2400")
    client.post(reverse("public:quote_add"), {"service": service.pk})

    client.post(reverse("public:quote_submit"), CONTACT_POST)

    assert client.get("/quote/").context["lines"] == []


def test_custom_requirements_can_be_submitted_without_catalogue_services(client):
    response = client.post(reverse("public:quote_submit"), CONTACT_POST)

    assert response.status_code == 302
    assert response.url == reverse("public:quote_sent")
    assert ContactSubmission.objects.count() == 1


def test_a_failed_quote_submission_keeps_the_selection(client):
    """Losing what someone spent five minutes choosing because they
    mistyped an email would be unforgivable."""
    from apps.catalog.tests.factories import make_service

    service = make_service("SEO retainer", price="2400")
    client.post(reverse("public:quote_add"), {"service": service.pk})

    response = client.post(reverse("public:quote_submit"),
                           {**CONTACT_POST, "email": "not-an-email"})

    assert response.status_code == 200
    assert len(client.get("/quote/").context["lines"]) == 1


def test_a_quote_request_notifies_quote_permission_holders(client):
    from apps.catalog.tests.factories import make_service
    from apps.notifications.models import Notification
    from apps.staff.tests.factories import make_role, make_staff_member

    quotes = make_staff_member("quotes@heliograph.agency",
                               roles=[make_role("Quotes", ["quotes_view"])])
    service = make_service("SEO retainer", price="2400")
    client.post(reverse("public:quote_add"), {"service": service.pk})

    client.post(reverse("public:quote_submit"), CONTACT_POST)

    assert Notification.objects.filter(recipient=quotes.user).exists()
