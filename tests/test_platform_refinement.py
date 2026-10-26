"""Feature boundaries, guest quotations and manual client commerce."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import make_user
from apps.analytics import services as reports
from apps.catalog.pricing import price_visible
from apps.catalog.tests.factories import make_service
from apps.core import operations
from apps.core.features import enabled
from apps.leads import guest, quote_services
from apps.leads.models import QuoteActivity, QuoteRequest, QuoteStatus
from apps.messaging import services as chat
from apps.organizations.tests.factories import make_member, make_tenant
from apps.permissions import access
from apps.permissions.services import create_role, set_role_permissions
from apps.staff import services as staff_services
from apps.staff.navigation import visible_navigation
from apps.staff.tests.factories import make_super_admin_user
from apps.subscriptions import changes, invoices, receipts
from apps.subscriptions.models import ClientSubscription, Invoice, PaymentReceipt
from apps.subscriptions.tests.factories import make_subscription

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace():
    admin = make_super_admin_user()
    owner = staff_services.create_staff_account(
        actor=admin, email="owner@agency.example", account_type="system_owner"
    ).user
    org, client = make_tenant("Client A")
    _, other = make_tenant("Client B")
    subscription = make_subscription(
        org, actor=admin, ends_on=timezone.localdate() + timedelta(days=30)
    )
    return admin, owner, org, client, other, subscription


def invoice_values(**extra):
    return {
        "reference": "INV-101",
        "description": "Agreed project deposit",
        "amount": Decimal("100"),
        "currency": "USD",
        "issued_on": timezone.localdate(),
        "due_on": timezone.localdate() + timedelta(days=14),
        **extra,
    }


def receipt_values(**extra):
    return {
        "reference": "PAY-101",
        "description": "Confirmed bank transfer",
        "amount": Decimal("40"),
        "currency": "USD",
        "paid_on": timezone.localdate(),
        "payment_method": "Bank transfer",
        **extra,
    }


def test_owner_category_has_business_permissions_but_not_feature_configuration(client, workspace):
    admin, owner, org, *_ = workspace
    assert owner.is_system_owner and owner.is_staff_member and not owner.is_super_admin
    assert access.can(owner, "cms_edit") and access.can(owner, "subscriptions_approve", org)
    assert not access.can(owner, "settings_manage")
    with pytest.raises(PermissionDenied):
        operations.update(actor=owner, values={"api_enabled": True})
    client.force_login(owner)
    assert client.get("/staff/settings/").status_code == 403
    keys = {item.key for group in visible_navigation(owner) for item in group["items"]}
    assert not {"settings", "integrations", "analytics"} & keys
    client.force_login(admin)
    assert client.get("/staff/settings/").status_code == 200


def test_disabled_modules_are_hidden_and_guarded_for_owner_and_client(client, workspace):
    admin, owner, org, recipient, *_ = workspace
    operations.update(
        actor=admin,
        values={
            "feature_flags": {"reports": False, "messages": False, "payments": False, "seo": False}
        },
    )
    for actor in [owner, recipient]:
        client.force_login(actor)
        for path in [
            "/organization/reports/",
            "/organization/messages/",
            "/organization/invoices/",
        ]:
            assert client.get(path).status_code == 404
    client.force_login(owner)
    assert client.get(f"/staff/seo/{org.slug}/").status_code in {403, 404}
    html = client.get(f"/staff/clients/{org.slug}/workspace/{recipient.pk}/").status_code
    assert html == 404
    client.force_login(recipient)
    html = client.get("/organization/").content
    assert b'href="/organization/reports/"' not in html
    assert b'href="/organization/messages/"' not in html
    assert b'href="/organization/invoices/"' not in html


def test_individual_integration_can_be_disabled_without_deleting_configuration(workspace):
    from apps.integrations.services import run_sync

    admin, *_ = workspace
    operations.update(
        actor=admin, values={"integrations_enabled": True, "feature_flags": {"meta_ads": False}}
    )
    assert enabled("google_ads") and not enabled("meta_ads")
    with patch("apps.integrations.providers.get_adapter") as adapter:
        assert run_sync(provider="meta_ads").status == "skipped"
    adapter.assert_not_called()


def test_tracking_tags_obey_individual_flags(client, workspace):
    from apps.tracking.models import TrackingSettings

    admin, *_ = workspace
    TrackingSettings.objects.update_or_create(
        pk=1, defaults={"meta_pixel_id": "123456789", "gtm_container_id": "GTM-TEST"}
    )
    operations.update(
        actor=admin,
        values={"analytics_enabled": True, "feature_flags": {"meta_pixel": False, "gtm": False}},
    )
    html = client.get("/").content
    assert b"123456789" not in html and b"GTM-TEST" not in html


def test_owner_cannot_elevate_staff_or_change_administrators(workspace):
    admin, owner, *_ = workspace
    for values in [
        {"account_type": "system_owner"},
        {"django_admin_access": True},
        {"has_all_client_access": True},
    ]:
        with pytest.raises(PermissionDenied):
            staff_services.create_staff_account(actor=owner, email="bad@example.com", **values)
    role = create_role(actor=owner, name="Delivery coordinator")
    with pytest.raises(PermissionDenied):
        set_role_permissions(actor=owner, role=role, codenames=["settings_manage"])
    admin_profile = staff_services.create_staff_account(
        actor=admin, email="second-admin@example.com", is_super_admin=True
    )
    with pytest.raises(PermissionDenied):
        staff_services.update_staff(actor=owner, profile=admin_profile, notes="Not allowed")
    with pytest.raises(PermissionDenied):
        staff_services.assign_roles(actor=owner, profile=admin_profile, roles=[])


def test_owner_can_create_and_remove_ordinary_staff(workspace):
    _, owner, *_ = workspace
    staff = staff_services.create_staff_account(actor=owner, email="assistant@example.com")
    staff_services.remove_staff_account(actor=owner, profile=staff)
    staff.user.refresh_from_db()
    assert staff.user.status == AccountStatus.DISABLED


def test_individual_service_visibility_overrides_hidden_default(client):
    shown = make_service("Visible price", price="9876", price_visibility="show")
    hidden = make_service("Private price", price="5432", price_visibility="hide")
    mode = operations.current()
    assert price_visible(shown, mode) and not price_visible(hidden, mode)
    assert b"9,876" in client.get(shown.get_absolute_url()).content
    assert b"5,432" not in client.get(hidden.get_absolute_url()).content
    mode.show_public_prices = True
    mode.save()
    assert b"5,432" not in client.get(hidden.get_absolute_url()).content


@pytest.mark.parametrize("with_service", [True, False])
def test_guest_request_has_private_followup_without_an_account(client, with_service):
    if with_service:
        service = make_service("Selected guest service")
        client.post("/quote/add/", {"service": service.pk})
    response = client.get("/quote/")
    assert response.status_code == 200
    response = client.post(
        "/quote/send/?guest=1",
        {
            "name": "Guest Person",
            "email": "guest@example.com",
            "message": "A custom launch campaign",
        },
    )
    assert response.status_code == 302
    quote = QuoteRequest.objects.get()
    assert quote.submitted_by_id is None
    assert quote.items.count() == int(with_service)
    token = client.session["guest_quote_token"]
    assert token not in quote.guest_access.token_hash
    url = reverse("public:guest_quote", args=[token])
    assert client.get(url).status_code == 200
    assert client.get(reverse("public:guest_quote", args=["guessed-token"])).status_code == 404
    client.post(url, {"action": "message", "body": "Please include the launch checklist."})
    assert quote.activities.filter(body__contains="launch checklist", is_internal=False).exists()


def test_guest_can_only_accept_published_proposal_and_never_reads_internal_notes(client, workspace):
    admin, *_ = workspace
    client.post(
        "/quote/send/?guest=1",
        {"name": "Guest", "email": "visitor@example.com", "message": "Custom strategy"},
    )
    quote = QuoteRequest.objects.get()
    token = client.session["guest_quote_token"]
    QuoteActivity.objects.create(quote=quote, body="CONFIDENTIAL INTERNAL NOTE", is_internal=True)
    with pytest.raises(ValidationError):
        guest.respond(token=token, action="accept")
    quote_services.change_status(quote=quote, actor=admin, status=QuoteStatus.REVIEWING)
    quote_services.change_status(quote=quote, actor=admin, status=QuoteStatus.PROPOSAL_READY)
    guest.respond(token=token, action="accept")
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.ACCEPTED
    with pytest.raises(ValidationError):
        guest.respond(token=token, action="decline")
    operations.update(actor=admin, values={"analytics_enabled": True})
    response = client.get(reverse("public:guest_quote", args=[token]))
    assert b"CONFIDENTIAL INTERNAL NOTE" not in response.content
    assert b"js/tracking.js" not in response.content
    assert "no-store" in response["Cache-Control"]
    assert response["Referrer-Policy"] == "no-referrer"
    quote.guest_access.expires_at = timezone.now() - timedelta(seconds=1)
    quote.guest_access.save()
    assert client.get(reverse("public:guest_quote", args=[token])).status_code == 404


def test_invoice_drafts_and_payments_are_private_and_balance_is_derived(client, workspace):
    admin, owner, org, recipient, other, subscription = workspace
    invoice = invoices.create(
        actor=owner,
        organization=org,
        client=recipient,
        subscription=subscription,
        **invoice_values(),
    )
    client.force_login(recipient)
    assert client.get(reverse("organizations:invoice", args=[invoice.pk])).status_code == 404
    invoices.publish(actor=owner, invoice=invoice)
    payment = receipts.issue(
        actor=owner, organization=org, client=recipient, invoice=invoice, **receipt_values()
    )
    assert Invoice.objects.get(pk=invoice.pk).balance == Decimal("60")
    assert client.get(reverse("organizations:invoice", args=[invoice.pk])).status_code == 200
    client.force_login(other)
    assert client.get(reverse("organizations:invoice", args=[invoice.pk])).status_code == 404
    with pytest.raises(ValidationError):
        receipts.issue(
            actor=admin,
            organization=org,
            client=recipient,
            invoice=invoice,
            **receipt_values(reference="PAY-OVER", amount=Decimal("80")),
        )
    with pytest.raises(ValidationError):
        invoices.void(actor=admin, invoice=invoice, reason="Correction")
    receipts.void(actor=admin, receipt=payment, reason="Payment reversed")
    assert Invoice.objects.get(pk=invoice.pk).balance == Decimal("100")
    invoices.void(actor=admin, invoice=invoice, reason="Replaced")
    assert Invoice.objects.get(pk=invoice.pk).payment_status == "Voided"


def test_payment_cannot_reference_another_recipient_or_currency(workspace):
    admin, _, org, recipient, _, _ = workspace
    colleague = make_user("finance@example.com")
    make_member(org, colleague)
    invoice = invoices.create(
        actor=admin, organization=org, client=recipient, publish=True, **invoice_values()
    )
    with pytest.raises(ValidationError):
        receipts.issue(
            actor=admin, organization=org, client=colleague, invoice=invoice, **receipt_values()
        )
    with pytest.raises(ValidationError):
        receipts.issue(
            actor=admin,
            organization=org,
            client=recipient,
            invoice=invoice,
            **receipt_values(currency="EUR"),
        )
    assert not PaymentReceipt.objects.exists()


def test_reports_include_private_service_details_and_downloads(client, workspace):
    admin, _, org, recipient, other, subscription = workspace
    upload = SimpleUploadedFile(
        "milestones.pdf", b"%PDF-1.4\nprivate document", content_type="application/pdf"
    )
    report = reports.create_report(
        actor=admin,
        organization=org,
        client=recipient,
        subscription=subscription,
        title="Launch report",
        summary="Work in progress",
        milestones="Discovery complete",
        completed_work="Research",
        attachment=upload,
    )
    attachment = report.attachments.get()
    url = reverse("organizations:report_attachment", args=[attachment.pk])
    client.force_login(recipient)
    assert client.get(url).status_code == 404
    reports.publish_report(actor=admin, report=report)
    response = client.get(url)
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")
    assert "attachment" in response["Content-Disposition"]
    client.force_login(other)
    assert client.get(url).status_code == 404
    with pytest.raises(ValidationError):
        reports.add_attachment(
            actor=admin, report=report, upload=SimpleUploadedFile("attack.svg", b"<svg/>")
        )


def test_message_references_cannot_cross_client_boundaries(workspace):
    admin, _, org, recipient, other, subscription = workspace
    message = chat.send(
        actor=recipient,
        organization=org,
        client=recipient,
        subscription=subscription,
        body="Could we extend this service?",
    )
    assert message.subscription == subscription
    other_subscription = make_subscription(
        other.organization_memberships.get().organization, actor=admin
    )
    with pytest.raises(ValidationError):
        chat.send(
            actor=admin,
            organization=org,
            client=recipient,
            subscription=other_subscription,
            body="Wrong client",
        )


@pytest.mark.parametrize("kind", ["extension", "renewal", "extra", "additional"])
def test_service_change_requires_quote_acceptance_and_is_applied_once(workspace, kind):
    admin, owner, org, recipient, _, subscription = workspace
    additional = make_service("Additional requested service") if kind == "additional" else None
    end = subscription.ends_on + timedelta(days=30)
    change = changes.request_change(
        actor=recipient,
        subscription=subscription,
        kind=kind,
        requirements="Please add the requested work",
        requested_end=end,
        additional_service=additional,
    )
    with pytest.raises(ValidationError):
        changes.apply(actor=owner, request_id=change.pk)
    quote = change.quote
    line = quote.items.get()
    line.quoted_amount, line.currency, line.billing_type = Decimal("250"), "USD", "monthly"
    line.save()
    quote_services.change_status(quote=quote, actor=owner, status=QuoteStatus.REVIEWING)
    quote_services.change_status(quote=quote, actor=owner, status=QuoteStatus.PROPOSAL_READY)
    quote_services.client_decision(quote=quote, actor=recipient, accepted=True)
    changes.apply(actor=owner, request_id=change.pk)
    first_applied = changes.apply(actor=owner, request_id=change.pk).applied_at
    assert first_applied
    subscription.refresh_from_db()
    if kind in {"extension", "renewal"}:
        assert subscription.ends_on == end
    if kind == "renewal":
        assert subscription.price == Decimal("250")
    if kind == "additional":
        assert ClientSubscription.objects.filter(
            organization=org, service=additional, status="active"
        ).exists()


def test_reports_and_payments_remain_available_with_chat_disabled(client, workspace):
    admin, owner, org, recipient, *_ = workspace
    operations.update(actor=admin, values={"feature_flags": {"messages": False}})
    client.force_login(owner)
    assert client.get("/staff/messages/").status_code == 200
    response = client.get(f"/staff/clients/{org.slug}/workspace/{recipient.pk}/")
    assert response.status_code == 200
    assert b"Progress reports" in response.content
    assert b"?tab=messages" not in response.content
    assert (
        client.get(f"/staff/clients/{org.slug}/workspace/{recipient.pk}/?tab=messages").status_code
        == 404
    )


def test_report_updates_preserve_recipient_and_publication(client, workspace):
    admin, owner, org, recipient, other, subscription = workspace
    report = reports.create_report(
        actor=owner,
        organization=org,
        client=recipient,
        title="Initial discovery",
        summary="Discovery underway",
        subscription=subscription,
        publish=True,
    )
    original = report.published_at
    report = reports.update_report(
        actor=owner,
        report=report,
        title="Discovery completed",
        progress=100,
        status="completed",
        completed_work="Research signed off",
    )
    assert report.published_at == original and report.progress == 100
    with pytest.raises(PermissionDenied):
        reports.update_report(actor=owner, report=report, client=other)
    with pytest.raises(PermissionDenied):
        reports.update_report(actor=recipient, report=report, progress=50)
    client.force_login(recipient)
    response = client.get("/organization/")
    assert b"Discovery completed" in response.content
    client.force_login(other)
    assert b"Discovery completed" not in client.get("/organization/").content


def test_disabled_service_area_is_hidden_from_combined_campaigns(workspace):
    from apps.campaigns import selectors as campaign_selectors
    from apps.campaigns.services import create_campaign, update_campaign

    admin, owner, org, recipient, *_ = workspace
    campaign = create_campaign(
        actor=admin, organization=org, name="Private disabled SEO", service_type="seo"
    )
    operations.update(actor=admin, values={"feature_flags": {"seo": False}})
    assert not campaign_selectors.visible_campaigns(owner).filter(pk=campaign.pk).exists()
    assert not campaign_selectors.campaigns_for_client(recipient).filter(pk=campaign.pk).exists()
    assert campaign_selectors.client_campaign(recipient, campaign.pk) is None
    with pytest.raises(PermissionDenied):
        update_campaign(actor=owner, campaign=campaign, name="Unavailable")
    assert campaign_selectors.get_campaign(admin, campaign.pk) is not None


def test_disabled_provider_cannot_be_configured_through_service(workspace):
    from apps.integrations.services import create_connection, set_credentials

    admin, owner, org, *_ = workspace
    operations.update(
        actor=admin, values={"integrations_enabled": True, "feature_flags": {"meta_ads": False}}
    )
    with pytest.raises(PermissionDenied):
        create_connection(actor=owner, provider="meta_ads", organization=org)
    with pytest.raises(PermissionDenied):
        set_credentials(actor=owner, provider="meta_ads", app_id="hidden")


def test_owner_can_edit_staff_identity_without_duplicate_email(workspace):
    _, owner, *_ = workspace
    profile = staff_services.create_staff_account(actor=owner, email="before@example.com")
    staff_services.update_staff(
        actor=owner, profile=profile, full_name="Delivery Assistant", email="after@example.com"
    )
    profile.user.refresh_from_db()
    assert profile.user.full_name == "Delivery Assistant"
    assert profile.user.email == "after@example.com"
    with pytest.raises(ValidationError):
        staff_services.update_staff(actor=owner, profile=profile, email=owner.email)


def test_owner_can_edit_public_form_labels_and_choices(client, workspace):
    from apps.cms import copy

    _, owner, *_ = workspace
    copy.update(actor=owner, key="public.forms.quote.message.label", text="Describe your launch")
    copy.update(
        actor=owner, key="public.forms.quote.objective.choice.brand", text="Grow recognition"
    )
    response = client.get("/quote/")
    assert b"Describe your launch" in response.content
    assert b"Grow recognition" in response.content
    response = client.post("/quote/send/?guest=1", {"message": "Needs a corrected email"})
    assert b"Describe your launch" in response.content


def test_disabled_features_hide_existing_notification_widgets(client, workspace):
    from apps.notifications import selectors as notifications
    from apps.notifications.services import notify

    admin, _, _, recipient, *_ = workspace
    notification = notify(
        recipient=recipient,
        title="Private report update",
        category="reports",
        url="/organization/reports/",
    )
    operations.update(actor=admin, values={"feature_flags": {"reports": False}})
    assert not notifications.for_user(recipient).filter(pk=notification.pk).exists()
    assert notifications.get_for_user(recipient, notification.pk) is None
    client.force_login(recipient)
    assert b"Private report update" not in client.get("/organization/").content
