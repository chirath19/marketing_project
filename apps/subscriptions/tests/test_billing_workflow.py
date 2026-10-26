"""References, linked receipts and correction history as one client workflow."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connections
from django.urls import reverse
from django.utils import timezone

from apps.organizations.tests.factories import make_tenant
from apps.permissions.management.commands.sync_permissions import sync_permissions
from apps.staff.tests.factories import make_super_admin_user
from apps.subscriptions import billing, invoices, receipts
from apps.subscriptions.models import Invoice, PaymentReceipt

pytestmark = pytest.mark.django_db


@pytest.fixture
def people():
    # Transactional tests flush migration-seeded permissions. Declare this
    # dependency explicitly so the concurrency tests also work after a flush.
    sync_permissions()
    org, customer = make_tenant("Billing studio", owner_email="billing-customer@example.com")
    admin = make_super_admin_user()
    return admin, org, customer


def invoice_values(**changes):
    return {"description": "Content strategy", "amount": Decimal("500"), "currency": "USD",
            "issued_on": timezone.localdate(), "due_on": timezone.localdate(), **changes}


def receipt_values(**changes):
    return {"description": "Confirmed transfer", "amount": Decimal("200"), "currency": "USD",
            "paid_on": timezone.localdate(), "payment_method": "Bank transfer", **changes}


def test_references_are_automatic_and_skip_existing_numbers(people):
    admin, org, customer = people
    prefix = f"INV-{timezone.localdate().year}-"
    old = invoices.create(actor=admin, organization=org, client=customer,
                          reference=prefix + "00001", **invoice_values())
    first = invoices.create(actor=admin, organization=org, client=customer, **invoice_values())
    second = invoices.create(actor=admin, organization=org, client=customer, **invoice_values())
    receipt = receipts.issue(actor=admin, organization=org, client=customer, **receipt_values())
    assert first.reference == prefix + "00002"
    assert second.reference == prefix + "00003"
    assert receipt.reference == f"RCT-{timezone.localdate().year}-00001"
    old.refresh_from_db()
    assert old.reference == prefix + "00001"


def test_repeat_submissions_do_not_duplicate_documents_or_payments(people):
    admin, org, customer = people
    invoice_key, receipt_key = uuid4(), uuid4()
    invoice = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                              submission_key=invoice_key, **invoice_values())
    repeated = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                               submission_key=invoice_key, **invoice_values())
    assert invoice.pk == repeated.pk
    payment = receipts.issue(actor=admin, organization=org, client=customer, invoice=invoice,
                             submission_key=receipt_key, **receipt_values(amount=Decimal("500")))
    repeated = receipts.issue(actor=admin, organization=org, client=customer, invoice=invoice,
                              submission_key=receipt_key, **receipt_values(amount=Decimal("500")))
    assert payment.pk == repeated.pk
    assert PaymentReceipt.objects.count() == 1
    assert Invoice.objects.get(pk=invoice.pk).balance == 0


def test_draft_edits_preserve_reference_and_issued_invoices_cannot_be_edited(people):
    admin, org, customer = people
    invoice = invoices.create(actor=admin, organization=org, client=customer, **invoice_values())
    reference = invoice.reference
    changed = invoices.update_draft(actor=admin, invoice=invoice, amount=Decimal("600"),
                                    description="Updated scope")
    assert changed.reference == reference and changed.amount == Decimal("600")
    invoices.publish(actor=admin, invoice=changed)
    with pytest.raises(ValidationError):
        invoices.update_draft(actor=admin, invoice=changed, amount=Decimal("700"))


def test_partial_payment_correction_restores_balance(people):
    admin, org, customer = people
    invoice = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                              **invoice_values())
    payment = receipts.issue(actor=admin, organization=org, client=customer, invoice=invoice,
                             **receipt_values())
    invoice.refresh_from_db()
    assert invoice.balance == Decimal("300")
    assert invoice.payment_status == "Partially paid"
    with pytest.raises(ValidationError):
        receipts.issue(actor=admin, organization=org, client=customer, invoice=invoice,
                       **receipt_values(amount=Decimal("400")))
    receipts.void(actor=admin, receipt=payment, reason="Transfer was reversed")
    invoice.refresh_from_db()
    assert invoice.balance == Decimal("500")
    assert PaymentReceipt.objects.get(pk=payment.pk).voided_at


def test_workspace_prefills_invoice_and_locks_recipient_currency(client, people):
    admin, org, customer = people
    invoice = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                              **invoice_values(currency="EUR"))
    client.force_login(admin)
    url = reverse("staff:client_desk", args=[org.slug, customer.pk])
    response = client.get(url + f"?tab=invoices&receive={invoice.pk}")
    form = response.context["receipt_form"]
    assert form.initial["invoice"] == invoice.pk and form.initial["amount"] == Decimal("500")
    assert form.fields["currency"].disabled and form.fields["invoice"].disabled
    assert "reference" not in form.fields
    data = receipt_values(amount="125", currency="USD")
    data.update(action="receipt", invoice="999999", submission_key=str(uuid4()))
    response = client.post(url + f"?tab=invoices&receive={invoice.pk}", data, follow=True)
    assert response.status_code == 200
    payment = PaymentReceipt.objects.get()
    assert payment.invoice_id == invoice.pk and payment.currency == "EUR"
    assert "Payment history &amp; receipts" in response.content.decode()
    assert payment.reference in response.content.decode()
    assert invoice.reference in response.content.decode()


def test_invoice_form_submission_generates_reference_and_supports_edit(client, people):
    admin, org, customer = people
    client.force_login(admin)
    url = reverse("staff:client_desk", args=[org.slug, customer.pk]) + "?tab=invoices"
    response = client.post(url, {"action": "invoice", **invoice_values(),
                                 "reference": "IGNORE-MANUALLY-POSTED", "submission_key": uuid4()})
    assert response.status_code == 302
    invoice = Invoice.objects.get()
    assert invoice.reference.startswith("INV-")
    response = client.post(url + f"&edit_invoice={invoice.pk}", {
        "action": "update_invoice", **invoice_values(amount="700"),
    })
    assert response.status_code == 302
    invoice.refresh_from_db()
    assert invoice.amount == Decimal("700")


def test_payment_summary_keeps_currencies_separate_and_excludes_voids(people):
    admin, org, customer = people
    usd = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                          **invoice_values())
    eur = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                          **invoice_values(currency="EUR", amount=Decimal("300")))
    draft = invoices.create(actor=admin, organization=org, client=customer, **invoice_values())
    payment = receipts.issue(actor=admin, organization=org, client=customer, invoice=usd,
                             **receipt_values())
    totals = {row["currency"]: row for row in billing.summary([usd, eur, draft], [payment])}
    assert totals["USD"]["balance"] == Decimal("300")
    assert totals["EUR"]["balance"] == Decimal("300")
    assert totals["EUR"]["received"] == 0


def test_client_sees_invoice_and_receipt_together_but_cannot_write(client, people):
    admin, org, customer = people
    invoice = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                              **invoice_values())
    payment = receipts.issue(actor=admin, organization=org, client=customer, invoice=invoice,
                             **receipt_values())
    client.force_login(customer)
    for route in ["organizations:client_invoices", "organizations:client_receipts"]:
        html = client.get(reverse(route)).content.decode()
        assert invoice.reference in html and payment.reference in html
        assert "Record payment &amp; issue receipt" not in html
    with pytest.raises(PermissionDenied):
        receipts.issue(actor=customer, organization=org, client=customer, **receipt_values())
    _, outsider = make_tenant("Elsewhere", owner_email="elsewhere@example.com")
    client.force_login(outsider)
    assert client.get(reverse("organizations:invoice", args=[invoice.pk])).status_code == 404
    receipt_url = reverse("organizations:payment_receipt", args=[payment.pk])
    assert client.get(receipt_url).status_code == 404


def test_invoice_receipt_links_are_present_on_both_documents(client, people):
    admin, org, customer = people
    invoice = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                              **invoice_values())
    payment = receipts.issue(actor=admin, organization=org, client=customer, invoice=invoice,
                             **receipt_values())
    client.force_login(customer)
    html = client.get(reverse("organizations:invoice", args=[invoice.pk])).content.decode()
    assert reverse("organizations:payment_receipt", args=[payment.pk]) in html
    html = client.get(reverse("organizations:payment_receipt", args=[payment.pk])).content.decode()
    assert reverse("organizations:invoice", args=[invoice.pk]) in html


@pytest.mark.django_db(transaction=True)
def test_concurrent_reference_allocation_is_unique(people):
    admin, org, customer = people
    barrier = Barrier(4)

    def issue(_):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return invoices.create(actor=admin, organization=org, client=customer,
                                   **invoice_values()).reference
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        references = list(pool.map(issue, range(4)))
    assert len(set(references)) == 4


@pytest.mark.django_db(transaction=True)
def test_concurrent_payments_cannot_exceed_invoice_balance(people):
    admin, org, customer = people
    barrier = Barrier(2)
    invoice = invoices.create(actor=admin, organization=org, client=customer, publish=True,
                              **invoice_values())

    def pay(_):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            receipts.issue(actor=admin, organization=org, client=customer, invoice=invoice,
                           **receipt_values(amount=Decimal("300")))
            return "paid"
        except ValidationError:
            return "refused"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, range(2)))
    assert sorted(results) == ["paid", "refused"]
    invoice.refresh_from_db()
    assert invoice.balance == Decimal("200")
