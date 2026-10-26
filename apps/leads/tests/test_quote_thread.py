"""One conversation per quote, and the client hearing about their quote."""

from __future__ import annotations

import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.leads import quote_services, quote_thread
from apps.leads.models import QuoteActivity, QuoteStatus
from apps.leads.tests.factories import make_quote_request
from apps.messaging.models import Message
from apps.notifications.models import Notification
from apps.organizations.tests.factories import make_member, make_org
from apps.staff.tests.factories import make_super_admin_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    admin = make_super_admin_user("boss@heliograph.agency")
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)
    quote = make_quote_request(submitted_by=user, organization=org)
    return admin, org, user, quote


def test_moving_to_proposal_ready_notifies_the_client(setup):
    admin, _org, user, quote = setup
    for status in (QuoteStatus.REVIEWING, QuoteStatus.PROPOSAL_READY):
        quote_services.change_status(quote=quote, status=status, actor=admin)

    notices = Notification.objects.filter(recipient=user, category="quote")
    assert list(notices.values_list("title", flat=True)) == [
        f"Your proposal {quote.reference} is ready for review"
    ]
    assert notices.get().url == quote.get_client_url()
    assert mail.outbox == []


def test_internal_moves_and_notes_do_not_notify_the_client(setup):
    admin, _org, user, quote = setup
    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING, actor=admin)
    quote_services.add_note(quote=quote, body="Check their budget", actor=admin)

    assert not Notification.objects.filter(recipient=user).exists()


def test_a_staff_reply_is_one_message_on_the_quote_and_in_the_conversation(client, setup):
    admin, _org, user, quote = setup
    client.force_login(admin)
    client.post(reverse("staff:quote_reply", args=[quote.pk]), {"body": "Can you share a date?"})

    message = Message.objects.get()
    assert message.quote == quote and message.conversation.client == user
    assert Notification.objects.filter(recipient=user, title__contains="New reply").exists()

    client.force_login(user)
    assert b"Can you share a date?" in client.get(quote.get_client_url()).content
    assert b"Can you share a date?" in client.get("/organization/messages/").content


def test_a_client_reply_on_the_quote_lands_in_the_conversation_too(client, setup):
    admin, _org, user, quote = setup
    client.force_login(user)
    client.post(reverse("organizations:quote_reply", args=[quote.pk]), {"body": "Yes, May 1."})

    assert Message.objects.get().body == "Yes, May 1."
    client.force_login(admin)
    assert b"Yes, May 1." in client.get(reverse("staff:quote_detail", args=[quote.pk])).content


def test_a_message_tagged_with_the_quote_in_chat_shows_on_the_quote(client, setup):
    from apps.messaging import services as messaging

    admin, org, user, quote = setup
    messaging.send(actor=user, organization=org, client=user, body="About that quote", quote=quote)

    client.force_login(user)
    assert b"About that quote" in client.get(quote.get_client_url()).content


def test_an_internal_note_from_the_composer_stays_internal(client, setup):
    admin, _org, user, quote = setup
    client.force_login(admin)
    client.post(reverse("staff:quote_reply", args=[quote.pk]),
                {"body": "Margin is thin", "mode": "note"})

    assert not Message.objects.exists()
    assert QuoteActivity.objects.get(body="Margin is thin").is_internal
    client.force_login(user)
    assert b"Margin is thin" not in client.get(quote.get_client_url()).content
    assert not Notification.objects.filter(recipient=user).exists()


def test_a_guest_quote_keeps_replies_on_its_timeline(setup):
    admin, *_ = setup
    quote = make_quote_request(email="walkin@example.com")

    entry = quote_thread.reply(quote=quote, actor=admin, body="Thanks for asking")

    assert isinstance(entry, QuoteActivity) and not entry.is_internal
    assert not Message.objects.exists()


def test_another_member_does_not_see_the_submitters_private_messages(setup):
    admin, org, _user, quote = setup
    colleague = make_user(email="sam@vantage.example")
    make_member(org, colleague)
    quote_thread.reply(quote=quote, actor=admin, body="Private to Priya")

    bodies = [entry.body for entry in quote_thread.entries(quote, colleague)]
    assert "Private to Priya" not in bodies


def test_opening_the_quote_reads_its_messages(client, setup):
    admin, _org, user, quote = setup
    quote_thread.reply(quote=quote, actor=admin, body="Hello")
    client.force_login(user)
    client.get(quote.get_client_url())

    assert Message.objects.get().read_at is not None
