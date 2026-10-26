"""Role parity and privacy for dashboard notification bells and unread indicators."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core import operations
from apps.leads.services import mark_read, record_submission
from apps.messaging import services as messaging
from apps.messaging.models import Conversation
from apps.notifications import selectors
from apps.notifications.services import notify
from apps.organizations.tests.factories import make_tenant
from apps.staff.services import create_staff_account
from apps.staff.tests.factories import make_staff_member, make_super_admin_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def people():
    admin = make_super_admin_user()
    owner = create_staff_account(
        actor=admin, email="owner@notices.example", account_type="system_owner"
    ).user
    org, customer = make_tenant("Notification client")
    _, outsider = make_tenant("Other client")
    return admin, owner, org, customer, outsider


@pytest.mark.parametrize("role", ["admin", "owner", "client"])
def test_each_role_has_a_bell_and_private_notification_inbox(client, people, role):
    admin, owner, org, customer, outsider = people
    actor = {"admin": admin, "owner": owner, "client": customer}[role]
    notify(recipient=actor, title="Your personal update")
    notify(recipient=outsider, title="Another client private update")
    client.force_login(actor)
    path = "/staff/dashboard/" if actor.is_staff_member else "/organization/"
    response = client.get(path)
    assert b"data-notification-bell" in response.content
    assert b"Notifications, 1 unread" in response.content
    inbox = client.get("/notifications/")
    assert inbox.status_code == 200
    assert b"Your personal update" in inbox.content
    assert b"Another client private update" not in inbox.content
    assert b"unread-highlight" in inbox.content
    counts = client.get("/notifications/summary/").json()
    assert counts["notifications"] == 1
    assert counts["enquiries"] == 0


def test_client_messages_notify_both_admin_and_owner_and_highlight_contact(client, people):
    admin, owner, org, customer, _ = people
    messaging.send(actor=customer, organization=org, client=customer, body="New client question")
    for actor in [admin, owner]:
        client.force_login(actor)
        summary = client.get("/notifications/summary/")
        assert summary.json()["messages"] == 1
        assert "no-store" in summary["Cache-Control"]
        response = client.get("/staff/messages/")
        assert b"unread-highlight" in response.content
        assert b"New messages" in response.content
    client.force_login(owner)
    response = client.get(reverse("staff:client_desk", args=[org.slug, customer.pk]))
    assert b"New client question" in response.content
    assert b"unread-highlight" in response.content
    assert client.get("/notifications/summary/").json()["messages"] == 0
    # The Admin has their own acknowledgement; an Owner cannot clear it for them.
    assert selectors.activity_summary(admin)["messages"] == 1


def test_client_sees_team_reply_and_reading_conversation_clears_alert(client, people):
    admin, _, org, customer, _ = people
    messaging.send(actor=admin, organization=org, client=customer, body="A reply to your enquiry")
    client.force_login(customer)
    assert client.get("/notifications/summary/").json()["messages"] == 1
    html = client.get("/organization/").content
    assert b'data-unread-kind="messages"' in html
    response = client.get("/organization/messages/")
    assert b"A reply to your enquiry" in response.content
    assert b"unread-highlight" in response.content
    assert client.get("/notifications/summary/").json()["messages"] == 0


def test_new_enquiry_notifies_admin_owner_but_not_clients_or_unprivileged_staff(client, people):
    admin, owner, _, customer, _ = people
    limited = make_staff_member("limited@notices.example").user
    submission = record_submission(
        name="Visitor",
        email="visitor@example.com",
        message="I would like to discuss a launch campaign.",
    )
    for actor in [admin, owner]:
        client.force_login(actor)
        counts = client.get("/notifications/summary/").json()
        assert counts["enquiries"] == 1 and counts["notifications"] == 1
        assert b"unread-highlight" in client.get("/staff/inbox/").content
    for actor in [customer, limited]:
        client.force_login(actor)
        counts = client.get("/notifications/summary/").json()
        assert counts["enquiries"] == 0 and counts["notifications"] == 0
    mark_read(submission=submission, actor=owner)
    assert selectors.activity_summary(owner)["notifications"] == 0
    assert selectors.activity_summary(owner)["enquiries"] == 0


def test_notification_actions_cannot_read_another_users_alert(client, people):
    admin, _, _, customer, _ = people
    notice = notify(recipient=admin, title="Admin only", url="/staff/dashboard/")
    client.force_login(customer)
    assert client.post(reverse("notifications:open", args=[notice.pk])).status_code == 404
    assert client.post("/notifications/read/").status_code == 302
    notice.refresh_from_db()
    assert notice.read_at is None


def test_open_is_post_only_and_refuses_external_redirects(client, people):
    _, _, _, customer, _ = people
    notice = notify(recipient=customer, title="Unsafe destination", url="https://external.example/")
    client.force_login(customer)
    url = reverse("notifications:open", args=[notice.pk])
    assert client.get(url).status_code == 405
    response = client.post(url)
    assert response.url == "/notifications/"
    notice.refresh_from_db()
    assert notice.read_at is not None


def test_polling_never_reads_messages_and_disabled_chat_disappears(client, people):
    admin, _, org, customer, _ = people
    message = messaging.send(actor=admin, organization=org, client=customer, body="Unread reply")
    client.force_login(customer)
    for _ in range(2):
        assert client.get("/notifications/summary/").json()["messages"] == 1
    message.refresh_from_db()
    assert message.read_at is None
    operations.update(actor=admin, values={"feature_flags": {"messages": False}})
    counts = client.get("/notifications/summary/").json()
    assert counts["messages"] == 0 and counts["notifications"] == 0
    assert b"Unread reply" not in client.get("/notifications/").content


def test_summary_requires_login_and_read_actions_require_csrf(people):
    _, _, _, customer, _ = people
    client = Client(enforce_csrf_checks=True)
    assert client.get("/notifications/summary/").status_code == 302
    client.force_login(customer)
    assert client.post("/notifications/read/").status_code == 403


def test_mark_all_read_keeps_conversation_unread_until_opened(client, people):
    admin, _, org, customer, _ = people
    message = messaging.send(actor=admin, organization=org, client=customer, body="Unread content")
    client.force_login(customer)
    client.post("/notifications/read/")
    assert client.get("/notifications/summary/").json()["notifications"] == 0
    message.refresh_from_db()
    assert message.read_at is None
    assert Conversation.objects.filter(client=customer).exists()


def test_multiple_messages_group_into_the_correct_conversation_count(people):
    admin, _, org, customer, _ = people
    for body in ["First question", "Second question"]:
        messaging.send(actor=customer, organization=org, client=customer, body=body)
    counts = selectors.activity_summary(admin)
    url = reverse("staff:client_desk", args=[org.slug, customer.pk])
    assert counts["messages"] == 2
    assert counts["message_threads"] == {url: 2}


def test_staff_reply_is_not_highlighted_as_incoming_for_another_staff_member(client, people):
    admin, owner, org, customer, _ = people
    messaging.send(actor=admin, organization=org, client=customer, body="Our team reply")
    client.force_login(owner)
    response = client.get(reverse("staff:client_desk", args=[org.slug, customer.pk]))
    assert b"conversation-message unread-highlight" not in response.content


def test_reading_quote_clears_its_request_badges_for_staff_and_own_alerts_for_client(
    client, people
):
    from apps.leads.models import QuoteRequest

    admin, owner, org, customer, outsider = people
    record_submission(
        name="Client",
        email=customer.email,
        message="A custom quotation request",
        kind="quote_request",
        submitted_by=customer,
        organization=org,
    )
    quote = QuoteRequest.objects.get(submitted_by=customer)
    notify(recipient=customer, title="Quote response", category="quote", url=quote.get_client_url())
    client.force_login(customer)
    assert client.get(quote.get_client_url()).status_code == 200
    assert selectors.activity_summary(customer)["notifications"] == 0
    assert selectors.activity_summary(admin)["quotes"] == 1
    client.force_login(owner)
    assert client.get(quote.get_absolute_url()).status_code == 200
    assert client.get("/notifications/summary/").json()["quotes"] == 0
    assert client.get("/notifications/summary/").json()["notifications"] == 0
    assert selectors.activity_summary(admin)["notifications"] > 0
    client.force_login(outsider)
    assert client.get(quote.get_client_url()).status_code == 404
