"""Private manual payment receipts. Issued records are corrected by voiding."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.messaging.policies import may_access
from apps.notifications.services import notify
from apps.subscriptions.billing import prepare_document
from apps.subscriptions.models import Invoice, PaymentReceipt


def for_client(actor, organization, client):
    rows = PaymentReceipt.objects.filter(organization=organization, client=client)
    if not may_access(actor, organization, client, "subscriptions_view"):
        return rows.none()
    return rows.select_related("client", "organization", "issued_by", "invoice", "subscription")


@transaction.atomic
def issue(*, actor, organization, client, **values):
    if not actor.is_staff_member or not may_access(
        actor, organization, client, "subscriptions_approve"
    ):
        raise PermissionDenied
    receipt = PaymentReceipt(organization=organization, client=client, issued_by=actor, **values)
    receipt.currency = receipt.currency.upper()
    from apps.messaging.references import validate

    validate(
        actor=actor, organization=organization, client=client, subscription=receipt.subscription
    )
    if receipt.invoice_id:
        invoice = Invoice.objects.select_for_update().get(pk=receipt.invoice_id)
    previous = prepare_document(receipt, "RCT")
    if previous:
        return previous
    if receipt.invoice_id:
        if invoice.organization_id != organization.pk or invoice.client_id != client.pk:
            raise ValidationError("Choose an invoice issued to this client.")
        if not invoice.published_at or invoice.voided_at:
            raise ValidationError("Only a published, valid invoice can receive a payment.")
        if invoice.currency != receipt.currency or receipt.amount > invoice.balance:
            raise ValidationError("Match the invoice currency and do not exceed its balance.")
        if receipt.subscription_id and receipt.subscription_id != invoice.subscription_id:
            raise ValidationError("The receipt service must match its invoice.")
        receipt.subscription = invoice.subscription

    receipt.full_clean()
    receipt.save()
    notify(
        recipient=client,
        title="Payment receipt available",
        body=receipt.reference,
        url=reverse("organizations:client_receipts"),
        category="receipts",
    )
    return receipt


@transaction.atomic
def void(*, actor, receipt, reason):
    if receipt.invoice_id:
        Invoice.objects.select_for_update().get(pk=receipt.invoice_id)
    receipt = PaymentReceipt.objects.select_for_update().get(pk=receipt.pk)
    if not actor.is_staff_member or not may_access(
        actor, receipt.organization, receipt.client, "subscriptions_approve"
    ):
        raise PermissionDenied
    if not reason.strip() or len(reason) > 300:
        raise ValidationError("Give a correction reason of 1–300 characters.")
    if not receipt.voided_at:
        receipt.voided_at, receipt.void_reason = timezone.now(), reason.strip()
        receipt.save(update_fields=["voided_at", "void_reason", "updated_at"])
        notify(
            recipient=receipt.client,
            title="A payment receipt was voided",
            body=f"{receipt.reference}: {receipt.void_reason}",
            url=reverse("organizations:client_receipts"),
            category="receipts",
        )
    return receipt


def get_receipt(actor, pk, organization=None):
    receipt = (
        PaymentReceipt.objects.select_related(
            "client", "organization", "issued_by", "invoice", "subscription"
        )
        .filter(pk=pk)
        .first()
    )
    if (
        receipt
        and (actor.is_staff_member or getattr(organization, "pk", None) == receipt.organization_id)
        and may_access(actor, receipt.organization, receipt.client, "subscriptions_view")
    ):
        return receipt
    return None
