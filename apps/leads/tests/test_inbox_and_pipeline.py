"""The staff Inbox, the lead pipeline, and who may touch them."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.leads import selectors, services
from apps.leads.models import ContactSubmission, Lead, LeadStatus, SubmissionKind
from apps.leads.tests.factories import make_lead, make_submission
from apps.staff.tests.factories import (
    PASSWORD,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def super_admin():
    return make_super_admin_user()


@pytest.fixture
def reader():
    """Can read the Inbox but change nothing."""
    return make_staff_member("reader@heliograph.agency",
                             roles=[make_role("Lead reader", ["leads_view"])])


@pytest.fixture
def worker():
    """Reads and works leads, but cannot hand them out."""
    return make_staff_member(
        "worker@heliograph.agency",
        roles=[make_role("Lead worker", ["leads_view", "leads_edit"])],
    )


@pytest.fixture
def nobody():
    return make_staff_member("nobody@heliograph.agency")


# --- authorisation --------------------------------------------------------------

STAFF_URLS = ["staff:module_inbox", "staff:module_leads", "staff:module_quotes"]


@pytest.mark.parametrize("url_name", STAFF_URLS)
def test_an_anonymous_visitor_is_sent_to_sign_in(client, url_name):
    response = client.get(reverse(url_name))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.parametrize("url_name", STAFF_URLS)
def test_a_client_user_is_refused(client, url_name):
    from apps.accounts.tests.factories import make_user

    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse(url_name)).status_code == 403


@pytest.mark.parametrize("url_name", STAFF_URLS)
def test_staff_without_the_permission_are_refused(client, nobody, url_name):
    sign_in(client, nobody.user)

    assert client.get(reverse(url_name)).status_code == 403


def test_a_client_cannot_read_their_own_enquiry(client):
    """Their own message is not a record they are entitled to browse."""
    from apps.accounts.tests.factories import make_user

    submission = make_submission(email="client@abc.example")
    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse("staff:inbox_detail",
                              args=[submission.pk])).status_code == 403


def test_a_reader_cannot_archive(client, reader):
    submission = make_submission()
    sign_in(client, reader.user)

    response = client.post(reverse("staff:inbox_archive", args=[submission.pk]),
                           {"archived": "1"})

    assert response.status_code == 403
    submission.refresh_from_db()
    assert not submission.is_archived


def test_a_worker_cannot_assign(client, worker):
    """Handing out work is a different decision from doing it."""
    lead = make_lead()
    sign_in(client, worker.user)

    response = client.post(reverse("staff:lead_assign", args=[lead.pk]),
                           {"assignee": worker.user.pk})

    assert response.status_code == 403
    lead.refresh_from_db()
    assert lead.assigned_to is None


# --- the Inbox -------------------------------------------------------------------


def test_the_inbox_lists_submissions(client, reader):
    make_submission(name="Someone Enquiring")
    sign_in(client, reader.user)

    assert b"Someone Enquiring" in client.get(reverse("staff:module_inbox")).content


def test_opening_a_submission_marks_it_read(client, reader):
    submission = make_submission()
    assert not submission.is_read
    sign_in(client, reader.user)

    client.get(reverse("staff:inbox_detail", args=[submission.pk]))
    submission.refresh_from_db()

    assert submission.is_read
    assert submission.read_by == reader.user


def test_a_submission_can_be_marked_unread(client, reader):
    submission = make_submission()
    sign_in(client, reader.user)
    client.get(reverse("staff:inbox_detail", args=[submission.pk]))

    client.post(reverse("staff:inbox_read", args=[submission.pk]), {"read": "0"})
    submission.refresh_from_db()

    assert not submission.is_read


def test_the_unread_view_shows_only_unread(client, reader):
    read = make_submission(name="Already Read")
    make_submission(name="Still Unread", email="other@example.com")
    services.mark_read(submission=read, actor=reader.user)
    sign_in(client, reader.user)

    body = client.get(reverse("staff:module_inbox"), {"view": "unread"}).content

    assert b"Still Unread" in body
    assert b"Already Read" not in body


def test_archiving_takes_it_out_of_the_inbox(client, worker):
    submission = make_submission(name="To Archive")
    sign_in(client, worker.user)

    client.post(reverse("staff:inbox_archive", args=[submission.pk]),
                {"archived": "1"})

    assert b"To Archive" not in client.get(reverse("staff:module_inbox")).content
    assert b"To Archive" in client.get(reverse("staff:module_inbox"),
                                       {"view": "archived"}).content


def test_an_archived_submission_is_kept(client, worker):
    submission = make_submission()
    services.set_archived(submission=submission, actor=worker.user, archived=True)

    assert ContactSubmission.objects.filter(pk=submission.pk).exists()


def test_spam_is_hidden_from_the_default_view_but_kept(client, worker):
    make_submission(name="Spammy One", is_spam=True, spam_reason="Contains links")
    sign_in(client, worker.user)

    assert b"Spammy One" not in client.get(reverse("staff:module_inbox")).content
    assert b"Spammy One" in client.get(reverse("staff:module_inbox"),
                                       {"view": "spam"}).content


def test_rescuing_a_false_positive_creates_the_lead_it_never_got(client, worker):
    """So a wrongly flagged enquiry can be recovered, not merely unhidden."""
    submission = make_submission(is_spam=True, spam_reason="Contains links")
    assert Lead.objects.count() == 0
    sign_in(client, worker.user)

    client.post(reverse("staff:inbox_spam", args=[submission.pk]), {"spam": "0"})
    submission.refresh_from_db()

    assert not submission.is_spam
    assert submission.lead is not None
    assert Lead.objects.count() == 1


def test_the_inbox_can_be_searched(client, reader):
    make_submission(name="Findable Person")
    make_submission(name="Other Person", email="other@example.com")
    sign_in(client, reader.user)

    body = client.get(reverse("staff:module_inbox"), {"q": "Findable"}).content

    assert b"Findable Person" in body
    assert b"Other Person" not in body


def test_the_quote_inbox_shows_only_quote_requests(client, super_admin):
    """The raw submissions behind quotes, filtered to that kind.

    `staff:module_quotes` is now the quote *pipeline*; the submissions
    themselves stay reachable at `staff:quote_inbox`, which is what this
    test is about.
    """
    make_submission(name="An Enquiry")
    make_submission(name="A Quote", email="quote@example.com",
                    kind=SubmissionKind.QUOTE_REQUEST)
    sign_in(client, super_admin)

    body = client.get(reverse("staff:quote_inbox")).content

    assert b"A Quote" in body
    assert b"An Enquiry" not in body


def test_the_submission_itself_is_never_editable(client, super_admin):
    """It is the record of what was actually sent."""
    submission = make_submission(message="The original words.")
    sign_in(client, super_admin)

    body = client.get(reverse("staff:inbox_detail", args=[submission.pk])).content

    assert b"The original words." in body
    assert b'name="message"' not in body


# --- the pipeline -----------------------------------------------------------------


def test_a_status_can_be_moved_forward(client, worker):
    lead = make_lead()
    sign_in(client, worker.user)

    client.post(reverse("staff:lead_status", args=[lead.pk]),
                {"status": LeadStatus.CONTACTED, "note": "Called them."})
    lead.refresh_from_db()

    assert lead.status == LeadStatus.CONTACTED
    assert lead.activities.filter(body="Called them.").exists()


def test_an_undefined_transition_is_refused(worker):
    """Declared as data, so an unexpected move raises rather than quietly
    rewriting history."""
    lead = make_lead(status=LeadStatus.NEW)

    with pytest.raises(ValidationError):
        services.change_status(lead=lead, new_status=LeadStatus.WON,
                               actor=worker.user)

    lead.refresh_from_db()
    assert lead.status == LeadStatus.NEW


def test_closing_a_lead_records_when(worker):
    lead = make_lead(status=LeadStatus.QUALIFIED)

    services.change_status(lead=lead, new_status=LeadStatus.WON, actor=worker.user)
    lead.refresh_from_db()

    assert lead.closed_at is not None


def test_assigning_notifies_the_new_owner(super_admin):
    from apps.notifications.models import Notification

    lead = make_lead()
    owner = make_staff_member("owner@heliograph.agency")

    services.assign(lead=lead, assignee=owner.user, actor=super_admin)

    notification = Notification.objects.get(recipient=owner.user)
    assert lead.name in notification.title


def test_assigning_to_yourself_does_not_notify_you(super_admin):
    from apps.notifications.models import Notification

    lead = make_lead()

    services.assign(lead=lead, assignee=super_admin, actor=super_admin)

    assert not Notification.objects.filter(recipient=super_admin).exists()


def test_a_lead_cannot_be_assigned_to_a_client(super_admin):
    from apps.accounts.tests.factories import make_user

    lead = make_lead()
    client_user = make_user(email="client@abc.example")

    with pytest.raises(ValidationError, match="assigned to staff"):
        services.assign(lead=lead, assignee=client_user, actor=super_admin)


def test_a_note_is_recorded_against_the_lead(worker):
    lead = make_lead()

    services.add_note(lead=lead, actor=worker.user, body="Spoke to them Tuesday.")

    activity = lead.activities.filter(kind="note").get()
    assert activity.body == "Spoke to them Tuesday."
    assert activity.actor == worker.user
    assert activity.is_internal


def test_an_empty_note_is_refused(worker):
    lead = make_lead()

    with pytest.raises(ValidationError):
        services.add_note(lead=lead, actor=worker.user, body="   ")


def test_internal_notes_are_staff_only(client, worker):
    """A client never sees them — there is no surface that shows them."""
    lead = make_lead()
    services.add_note(lead=lead, actor=worker.user, body="SECRET INTERNAL NOTE")

    from apps.accounts.tests.factories import make_user

    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse("staff:lead_detail",
                              args=[lead.pk])).status_code == 403


def test_the_pipeline_can_be_filtered_by_status(client, reader):
    make_lead("New One", email="new@example.com", status=LeadStatus.NEW)
    make_lead("Won One", email="won@example.com", status=LeadStatus.WON)
    sign_in(client, reader.user)

    body = client.get(reverse("staff:module_leads"), {"status": "won"}).content

    assert b"Won One" in body
    assert b"New One" not in body


def test_the_unassigned_filter_finds_leads_nobody_owns(client, reader,
                                                       super_admin):
    owned = make_lead("Owned", email="owned@example.com")
    make_lead("Orphan", email="orphan@example.com")
    services.assign(lead=owned, assignee=super_admin, actor=super_admin)
    sign_in(client, reader.user)

    body = client.get(reverse("staff:module_leads"), {"owner": "unassigned"}).content

    assert b"Orphan" in body
    assert b"Owned" not in body


# --- dashboard metrics -------------------------------------------------------------


def test_the_dashboard_counts_are_real(reader, super_admin):
    make_submission(name="Unread one")
    read = make_submission(name="Read one", email="read@example.com")
    services.mark_read(submission=read, actor=reader.user)
    make_lead("Assigned", email="assigned@example.com")

    counts = selectors.inbox_counts(reader.user)

    assert counts["unread"] == 1
    assert counts["new_leads"] >= 1
    assert counts["unassigned"] >= 1


def test_the_dashboard_counts_are_one_query_each_table(reader,
                                                       django_assert_num_queries):
    """Two aggregates, one per table — not three round trips for three
    numbers.

    The actor's permissions are resolved first, because that is cached per
    request anyway; counting it here would measure the permission system
    rather than this query.
    """
    from apps.permissions.access import permission_codenames_for

    make_submission()
    permission_codenames_for(reader.user)

    with django_assert_num_queries(2):
        selectors.inbox_counts(reader.user)


def test_someone_without_the_permission_sees_zeroes(nobody):
    make_submission()

    counts = selectors.inbox_counts(nobody.user)

    assert counts == {"unread": 0, "new_leads": 0, "unassigned": 0}


def test_the_dashboard_shows_the_enquiry_metrics(client, reader):
    make_submission()
    sign_in(client, reader.user)

    body = client.get(reverse("staff:dashboard")).content

    assert b"Unread enquiries" in body
    assert b"Unassigned leads" in body


# --- notifications ------------------------------------------------------------------


def test_a_person_sees_only_their_own_notifications(client, reader):
    from apps.notifications.services import notify

    other = make_staff_member("other@heliograph.agency")
    notify(recipient=other.user, title="NOT FOR YOU")
    notify(recipient=reader.user, title="FOR YOU")
    sign_in(client, reader.user)

    body = client.get(reverse("staff:module_notifications")).content

    assert b"FOR YOU" in body
    assert b"NOT FOR YOU" not in body


def test_opening_someone_elses_notification_is_a_404(client, reader):
    from apps.notifications.services import notify

    other = make_staff_member("other@heliograph.agency")
    notification = notify(recipient=other.user, title="Theirs")
    sign_in(client, reader.user)

    assert client.get(reverse("staff:notification_open",
                              args=[notification.pk])).status_code == 404


def test_opening_a_notification_marks_it_read(client, reader):
    from apps.notifications.services import notify

    notification = notify(recipient=reader.user, title="Yours", url="/staff/leads/")
    sign_in(client, reader.user)

    client.get(reverse("staff:notification_open", args=[notification.pk]))
    notification.refresh_from_db()

    assert notification.is_read


def test_mark_all_read_clears_the_badge(client, reader):
    from apps.notifications.selectors import unread_count
    from apps.notifications.services import notify

    for index in range(3):
        notify(recipient=reader.user, title=f"Item {index}")
    sign_in(client, reader.user)

    client.post(reverse("staff:notifications_read"))

    assert unread_count(reader.user) == 0


def test_a_client_cannot_reach_the_notification_centre(client):
    from apps.accounts.tests.factories import make_user

    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse("staff:module_notifications")).status_code == 403
