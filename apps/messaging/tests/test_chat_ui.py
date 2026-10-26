"""A consistent conversation surface without changing who can read each thread."""

import pytest
from django.urls import reverse

from apps.leads import quote_services, quote_thread
from apps.leads.models import QuoteActivity
from apps.leads.tests.factories import make_quote_request
from apps.messaging import services
from apps.messaging.models import Message
from apps.organizations.tests.factories import make_tenant
from apps.staff.tests.factories import make_super_admin_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation():
    admin = make_super_admin_user()
    org, client = make_tenant("Chat Studio", owner_email="chat-client@example.com")
    quote = make_quote_request(organization=org, submitted_by=client)
    return admin, org, client, quote


@pytest.mark.parametrize("staff", [True, False])
def test_quote_and_messages_share_controls_and_messages(client, conversation, staff):
    admin, org, customer, quote = conversation
    quote_thread.reply(quote=quote, actor=admin, body="A shared conversation")
    quote_services.add_note(quote=quote, actor=admin, body="Private pricing discussion")
    client.force_login(admin if staff else customer)
    quote_url = quote.get_absolute_url() if staff else quote.get_client_url()
    messages_url = reverse("staff:client_desk", args=[org.slug, customer.pk]) if staff else (
        reverse("organizations:client_desk")
    )
    for url in [quote_url, messages_url]:
        response = client.get(url)
        html = response.content.decode()
        assert response.status_code == 200
        assert "A shared conversation" in html
        for control in ["data-chat-search", "data-chat-copy", "data-chat-expand",
                        "data-chat-latest", 'maxlength="5000"', 'hx-sync=', 'data-chat-form']:
            assert control in html
        if not staff or url == messages_url:
            assert "Private pricing discussion" not in html
    assert ("Private pricing discussion" in client.get(quote_url).content.decode()) is staff


@pytest.mark.parametrize("staff", [True, False])
def test_invalid_quote_reply_retains_draft_and_errors(client, conversation, staff):
    admin, _org, customer, quote = conversation
    client.force_login(admin if staff else customer)
    url = reverse("staff:quote_reply" if staff else "organizations:quote_reply", args=[quote.pk])
    draft = "A" * 5001
    response = client.post(url, {"body": draft, "mode": "note"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    html = response.content.decode()
    assert draft in html and 'class="chat-errors"' in html
    assert not Message.objects.exists()
    assert not QuoteActivity.objects.filter(body=draft).exists()
    if staff:
        assert 'class="chat-composer is-note"' in html


@pytest.mark.parametrize("staff", [True, False])
def test_quote_reply_accepts_same_limit_as_messages(client, conversation, staff):
    admin, _org, customer, quote = conversation
    client.force_login(admin if staff else customer)
    response = client.post(
        reverse("staff:quote_reply" if staff else "organizations:quote_reply", args=[quote.pk]),
        {"body": "A" * 5000}, HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 302
    assert Message.objects.get().body == "A" * 5000


def test_reading_older_history_then_sending_returns_to_latest(client, conversation):
    admin, org, customer, _quote = conversation
    client.force_login(customer)
    thread = services.send(
        actor=admin, organization=org, client=customer, body="First",
    ).conversation
    Message.objects.bulk_create([
        Message(conversation=thread, sender=admin, body=f"Message {index}") for index in range(55)
    ])
    response = client.post(reverse("organizations:client_desk") + "?page=2", {
        "action": "message", "body": "The newest reply",
    }, follow=True)
    assert response.context["message_page"].number == 1
    assert "The newest reply" in response.content.decode()


def test_staff_messages_have_same_alignment_on_both_surfaces(client, conversation):
    admin, org, customer, quote = conversation
    colleague = make_super_admin_user("other-team@example.com")
    quote_thread.reply(quote=quote, actor=colleague, body="From a teammate")
    client.force_login(admin)
    rows = client.get(reverse("staff:client_desk", args=[org.slug, customer.pk])).context[
        "chat_messages"
    ]
    assert rows[0].outgoing
    assert quote_thread.entries(quote, admin)[-1].outgoing


def test_internal_notes_start_their_own_group(conversation):
    admin, _org, _customer, quote = conversation
    quote_thread.reply(quote=quote, actor=admin, body="Visible to the client")
    quote_services.add_note(quote=quote, actor=admin, body="Private to the team")
    note = quote_thread.entries(quote, admin)[-1]
    assert note.is_internal and note.starts_group
    assert not note.has_receipt
