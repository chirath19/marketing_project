"""Manual client service journey and its privacy boundaries."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import make_user
from apps.analytics import services as reports
from apps.analytics.models import ClientReport
from apps.catalog.tests.factories import make_package, make_service
from apps.cms import copy
from apps.core.models import OperatingSettings
from apps.core.operations import current
from apps.integrations.models import SyncStatus
from apps.integrations.services import run_sync
from apps.leads.models import QuoteRequest, QuoteStatus
from apps.leads.quote_services import change_status
from apps.messaging import services as chat
from apps.messaging.models import Message
from apps.notifications.models import Notification
from apps.organizations.tests.factories import make_member, make_tenant
from apps.staff.tests.factories import (
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)
from apps.subscriptions import receipts
from apps.subscriptions.models import PaymentReceipt
from apps.tracking.services import record_event

pytestmark = pytest.mark.django_db


@pytest.fixture
def people():
    org, owner = make_tenant("Manual client")
    second = make_user("colleague@example.com")
    make_member(org, second)
    other_org, outsider = make_tenant("Other client")
    admin = make_super_admin_user()
    return org, owner, second, other_org, outsider, admin


def receipt_values():
    return {
        "reference": "PAY-001",
        "description": "Strategy project deposit",
        "amount": Decimal("450.00"),
        "currency": "USD",
        "paid_on": timezone.localdate(),
        "payment_method": "Bank transfer",
    }


def test_new_install_defaults_to_manual_mode():
    mode = current()
    assert not mode.integrations_enabled
    assert not mode.api_enabled
    assert not mode.analytics_enabled
    assert not mode.show_public_prices
    assert not mode.require_quote_account


def test_disabled_integrations_skip_without_constructing_adapter():
    with patch("apps.integrations.providers.get_adapter") as adapter:
        run = run_sync(provider="meta_ads")
    assert run.status == SyncStatus.SKIPPED
    assert "disabled" in run.error_summary
    adapter.assert_not_called()


def test_tracking_is_off_in_browser_and_server(client):
    assert b"js/tracking.js" not in client.get("/").content
    assert client.post("/t/event/").status_code == 404
    assert record_event(event_name="page_view", path="/") is None


def test_api_can_be_enabled_without_enabling_external_sync(client, people):
    admin = people[-1]
    client.force_login(admin)
    assert client.get("/api/v1/organizations/").status_code == 404
    client.post("/staff/settings/", {"api_enabled": "on", "require_quote_account": "on"})
    assert client.get("/api/v1/organizations/").status_code == 200
    assert not current().integrations_enabled
    client.post("/staff/settings/", {})
    assert not current().api_enabled


def test_client_cannot_change_operating_mode(client, people):
    client.force_login(people[1])
    assert client.post("/staff/settings/", {"api_enabled": "on"}).status_code in {403, 404}
    assert not current().api_enabled


def test_public_prices_and_structured_offers_are_hidden_until_enabled(client):
    service = make_service("Private prices", price="8765")
    make_package(service, price="4321")
    for path in ["/services/", service.get_absolute_url()]:
        html = client.get(path).content
        assert b"$8,765" not in html and b"$4,321" not in html
        assert b'"@type": "Offer"' not in html
    OperatingSettings.objects.filter(pk=1).update(show_public_prices=True)
    assert b"$8,765" in client.get(service.get_absolute_url()).content


def test_quote_review_requires_signin_without_losing_selection(client):
    OperatingSettings.objects.filter(pk=1).update(require_quote_account=True)
    service = make_service("Selected")
    client.post("/quote/add/", {"service": service.pk})
    response = client.get("/quote/", follow=True)
    assert "/accounts/login/" in response.redirect_chain[-1][0]
    assert client.session["quote_selection"] == [f"{service.pk}:"]


@pytest.mark.parametrize("as_admin", [True, False])
def test_staff_quote_entry_explains_client_account_and_preserves_selection(client, as_admin):
    actor = make_super_admin_user() if as_admin else make_staff_member().user
    service = make_service("Saved staff selection")
    client.force_login(actor)
    client.post("/quote/add/", {"service": service.pk})
    response = client.get("/organization/quotes/new/", follow=True)
    assert response.status_code == 200
    assert b"You are signed in with a staff account" in response.content
    assert b"Staff dashboard" in response.content
    assert client.session["quote_selection"] == [f"{service.pk}:"]
    response = client.post("/organization/quotes/new/", {"message": "Not a client request"})
    assert response.status_code == 200
    assert not QuoteRequest.objects.exists()


@pytest.mark.parametrize("status", ["pending", "suspended", "archived"])
def test_inactive_workspace_quote_entry_explains_status_without_submitting(client, status):
    org, owner = make_tenant("Awaiting agency", org_status=status)
    client.force_login(owner)
    service = make_service("Saved client selection")
    client.post("/quote/add/", {"service": service.pk})
    expected_notice = b"awaiting approval" if status == "pending" else b"not active"
    for response in [
        client.get("/organization/quotes/new/"),
        client.post("/organization/quotes/new/", {"message": "Wait for approval"}),
    ]:
        assert response.status_code == 200
        assert expected_notice in response.content
        assert b"selected services are still saved" in response.content
    assert not QuoteRequest.objects.exists()
    assert client.session["quote_selection"] == [f"{service.pk}:"]
    org.status = "active"
    org.save(update_fields=["status"])
    assert b"Send quotation request" in client.get("/organization/quotes/new/").content


def test_quote_entry_without_workspace_continues_to_setup(client):
    client.force_login(make_user("needs-workspace@example.com"))
    response = client.get("/organization/quotes/new/", follow=True)
    assert response.status_code == 200
    assert response.redirect_chain == [(reverse("organizations:setup"), 302)]


@pytest.mark.parametrize("custom_only", [True, False])
def test_client_submits_service_or_custom_request(client, people, custom_only):
    org, owner, *_ = people
    client.force_login(owner)
    service = make_service("Service")
    response = client.post(
        "/organization/quotes/new/",
        {
            "services": [] if custom_only else [service.pk],
            "message": "Please prepare a tailored launch plan.",
        },
    )
    assert response.status_code == 302
    quote = QuoteRequest.objects.get(submitted_by=owner)
    assert quote.organization == org
    assert quote.notes == "Please prepare a tailored launch plan."
    assert quote.items.count() == (0 if custom_only else 1)
    if not custom_only:
        assert quote.items.get().price_display == ""
    assert quote.status == QuoteStatus.NEW


def test_saved_package_is_carried_into_client_request(client, people):
    service = make_service("Tiered")
    package = make_package(service)
    client.post("/quote/add/", {"service": service.pk, "package": package.pk})
    client.force_login(people[1])
    client.post("/organization/quotes/new/", {"services": [service.pk]})
    quote = QuoteRequest.objects.get(submitted_by=people[1])
    assert quote.items.get().package == package


def test_empty_or_foreign_catalogue_request_is_rejected(client, people):
    client.force_login(people[1])
    for data in [{}, {"services": [99999999]}]:
        assert client.post("/organization/quotes/new/", data).status_code == 200
    assert not QuoteRequest.objects.exists()


def test_admin_can_price_a_custom_request_and_client_can_accept(client, people):
    org, owner, second, _, _, admin = people
    client.force_login(owner)
    client.post("/organization/quotes/new/", {"message": "Custom strategy workshop"})
    quote = QuoteRequest.objects.get(submitted_by=owner)
    client.force_login(admin)
    response = client.post(
        reverse("staff:quote_add_line", args=[quote.pk]),
        {
            "name": "Strategy workshop",
            "quoted_amount": "1200.00",
            "currency": "USD",
            "billing_type": "one_time",
        },
    )
    assert response.status_code == 302
    assert quote.items.get().quoted_amount == Decimal("1200")
    change_status(quote=quote, actor=admin, status=QuoteStatus.REVIEWING)
    change_status(quote=quote, actor=admin, status=QuoteStatus.PROPOSAL_READY)
    client.force_login(second)
    assert client.get(reverse("organizations:quote_detail", args=[quote.pk])).status_code == 404
    client.force_login(owner)
    response = client.post(
        reverse("organizations:quote_decision", args=[quote.pk]), {"decision": "accept"}
    )
    assert response.status_code == 302
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.ACCEPTED


def test_chat_is_private_even_between_two_clients_in_same_company(client, people):
    org, owner, second, _, outsider, admin = people
    chat.send(actor=admin, organization=org, client=owner, body="Private launch details")
    client.force_login(owner)
    assert b"Private launch details" in client.get("/organization/messages/").content
    for user in [second, outsider]:
        client.force_login(user)
        assert b"Private launch details" not in client.get("/organization/messages/").content
    with pytest.raises(PermissionDenied):
        chat.send(actor=second, organization=org, client=owner, body="Impersonation")


def test_client_message_notifies_only_authorized_assigned_staff(people):
    org, owner, _, _, _, admin = people
    role = make_role("Messenger", ["messaging_view", "messaging_create"])
    assigned = make_staff_member("assigned@example.com", roles=[role])
    unassigned = make_staff_member("unassigned@example.com", roles=[role])
    assign_client(assigned, org)
    chat.send(actor=owner, organization=org, client=owner, body="Can we discuss the brief?")
    ids = set(
        Notification.objects.filter(category="messaging").values_list("recipient_id", flat=True)
    )
    assert admin.pk in ids and assigned.user_id in ids
    assert unassigned.user_id not in ids
    with pytest.raises(PermissionDenied):
        chat.send(actor=unassigned.user, organization=org, client=owner, body="No access")


def test_chat_read_state_and_escaped_content(client, people):
    org, owner, _, _, _, admin = people
    message = chat.send(
        actor=owner, organization=org, client=owner, body="<script>alert(1)</script>"
    )
    client.force_login(admin)
    response = client.get(reverse("staff:client_desk", args=[org.slug, owner.pk]))
    assert b"&lt;script&gt;" in response.content
    message.refresh_from_db()
    assert message.read_at is not None
    assert Message.objects.count() == 1


def test_reports_require_publication_and_correct_recipient(client, people):
    org, owner, second, _, _, admin = people
    report = reports.create_report(
        actor=admin,
        organization=org,
        client=owner,
        title="Draft discovery",
        summary="Confidential progress",
        progress=40,
    )
    client.force_login(owner)
    assert b"Confidential progress" not in client.get("/organization/reports/").content
    reports.publish_report(actor=admin, report=report)
    assert b"Confidential progress" in client.get("/organization/reports/").content
    client.force_login(second)
    assert b"Confidential progress" not in client.get("/organization/reports/").content
    assert ClientReport.objects.count() == 1


def test_client_cannot_publish_reports(client, people):
    org, owner, _, _, _, admin = people
    report = reports.create_report(
        actor=admin, organization=org, client=owner, title="Draft", summary="Work"
    )
    client.force_login(owner)
    response = client.post("/organization/reports/", {"action": "publish", "record": report.pk})
    assert response.status_code == 403
    report.refresh_from_db()
    assert report.published_at is None


def test_receipt_is_private_printable_and_void_history_remains(client, people):
    org, owner, second, _, outsider, admin = people
    receipt = receipts.issue(actor=admin, organization=org, client=owner, **receipt_values())
    url = reverse("organizations:payment_receipt", args=[receipt.pk])
    client.force_login(owner)
    assert b"450.00" in client.get(url).content
    for user in [second, outsider]:
        client.force_login(user)
        assert client.get(url).status_code == 404
    receipts.void(actor=admin, receipt=receipt, reason="Duplicate acknowledgement")
    receipt.refresh_from_db()
    assert receipt.voided_at and receipt.amount == Decimal("450.00")
    client.force_login(owner)
    assert b"VOIDED" in client.get(url).content
    assert PaymentReceipt.objects.count() == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", Decimal("-1")),
        ("currency", "????"),
        ("paid_on", timezone.localdate() + timedelta(days=1)),
    ],
)
def test_receipts_reject_invalid_payment_records(people, field, value):
    org, owner, _, _, _, admin = people
    values = receipt_values()
    values[field] = value
    with pytest.raises(ValidationError):
        receipts.issue(actor=admin, organization=org, client=owner, **values)
    assert not PaymentReceipt.objects.exists()


def test_revoked_membership_blocks_saved_conversations_and_documents(client, people):
    org, owner, _, _, _, admin = people
    chat.send(actor=admin, organization=org, client=owner, body="Previously visible")
    receipt = receipts.issue(actor=admin, organization=org, client=owner, **receipt_values())
    org.memberships.filter(user=owner).update(status="removed")
    client.force_login(owner)
    assert (
        client.get(reverse("organizations:payment_receipt", args=[receipt.pk])).status_code == 404
    )


def test_staff_can_create_roles_and_set_real_permissions(client, people):
    from apps.permissions.models import Role

    client.force_login(people[-1])
    response = client.post(
        "/staff/roles/new/", {"name": "Client care", "description": "Service team"}
    )
    assert response.status_code == 302
    role = Role.objects.get(name="Client care")
    client.post(
        reverse("staff:role_set_permissions", args=[role.pk]),
        {
            "permissions": ["messaging_view", "messaging_create", "analytics_view"],
        },
    )
    assert role.permission_codenames == {"messaging_view", "messaging_create", "analytics_view"}


def test_website_copy_is_editable_escaped_and_resettable(client, people):
    key = next(key for key in copy.defaults() if key.startswith("public.catalog.index."))
    copy.update(actor=people[-1], key=key, text="<b>Our service studio</b>")
    html = client.get("/services/").content
    assert b"&lt;b&gt;Our service studio&lt;/b&gt;" in html
    assert b"<b>Our service studio</b>" not in html
    with pytest.raises(PermissionDenied):
        copy.update(actor=people[1], key=key, text="Changed")
    copy.update(actor=people[-1], key=key, text="", reset=True)
    assert b"Our service studio" not in client.get("/services/").content


def test_owner_approves_registration_and_its_workspace(client, people):
    from django.test import override_settings

    from apps.accounts.services import register_client
    from apps.accounts.tests.factories import PASSWORD

    with override_settings(ACCOUNTS_REGISTRATION_MODE="approval"):
        result = register_client(
            email="pending-journey@example.com",
            password=PASSWORD,
            full_name="New client",
            company_name="Pending company",
        )
    client.force_login(people[-1])
    response = client.post(reverse("staff:registration_approve", args=[result.user.pk]))
    assert response.status_code == 302
    result.user.refresh_from_db()
    result.organization.refresh_from_db()
    assert result.user.is_active and result.organization.status == "active"
    client.force_login(result.user)
    assert client.get("/organization/quotes/new/").status_code == 200


def test_unassigned_staff_cannot_read_or_modify_client_quote(client, people):
    from apps.leads.quote_services import add_note
    from apps.leads.tests.factories import make_quote_request

    org, owner, *_ = people
    quote = make_quote_request(submitted_by=owner, organization=org)
    staff = make_staff_member(roles=[make_role("Quote access", ["quotes_view", "quotes_edit"])])
    client.force_login(staff.user)
    assert client.get(reverse("staff:quote_detail", args=[quote.pk])).status_code == 404
    with pytest.raises(PermissionDenied):
        add_note(actor=staff.user, quote=quote, body="Cannot write")


def test_accepted_quote_scope_cannot_be_rewritten(people):
    from apps.leads.quote_services import update_scope
    from apps.leads.tests.factories import make_quote_request

    quote = make_quote_request()
    quote.status = QuoteStatus.ACCEPTED
    quote.save(update_fields=["status"])
    with pytest.raises(ValidationError):
        update_scope(actor=people[-1], quote=quote, summary="Different agreement")


def test_report_only_staff_can_open_their_client_desk(client, people):
    org, owner, *_ = people
    staff = make_staff_member(roles=[make_role("Reporter", ["analytics_view", "analytics_create"])])
    assign_client(staff, org)
    client.force_login(staff.user)
    response = client.get(reverse("staff:client_desk", args=[org.slug, owner.pk]))
    assert response.status_code == 200 and response.context["tab"] == "reports"


def test_clients_cannot_access_each_others_receipts_by_switching_org(client, people):
    org, owner, _, other_org, outsider, admin = people
    make_member(other_org, owner)
    receipt = receipts.issue(actor=admin, organization=org, client=owner, **receipt_values())
    client.force_login(owner)
    from apps.organizations.middleware import SESSION_KEY

    session = client.session
    session[SESSION_KEY] = other_org.pk
    session.save()
    assert (
        client.get(reverse("organizations:payment_receipt", args=[receipt.pk])).status_code == 404
    )
