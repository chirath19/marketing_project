"""Reference allocation and summaries shared by invoices and receipts."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.subscriptions.models import BillingSequence


@transaction.atomic
def prepare_document(document, prefix):
    """Hold the counter lock until the caller's issuance transaction commits.

    Existing references are retained for imports. Dashboard forms supply a
    submission key so repeating a successful POST returns its original record.
    """
    key = f"{prefix}-{timezone.localdate().year}"
    counter, _ = BillingSequence.objects.get_or_create(key=key)
    counter = BillingSequence.objects.select_for_update().get(pk=counter.pk)
    if document.submission_key:
        previous = type(document).objects.filter(submission_key=document.submission_key).first()
        if previous:
            if (previous.organization_id != document.organization_id
                    or previous.client_id != document.client_id):
                raise ValidationError("This submission was already used for another client.")
            return previous
    if not document.reference:
        while True:
            counter.value += 1
            reference = f"{key}-{counter.value:05d}"
            if not type(document).objects.filter(reference=reference).exists():
                break
        counter.save(update_fields=["value"])
        document.reference = reference
    return None


def summary(invoice_rows, receipt_rows):
    """Never add together amounts denominated in different currencies."""
    totals = {}
    for invoice in invoice_rows:
        if not invoice.published_at or invoice.voided_at:
            continue
        row = totals.setdefault(invoice.currency, {
            "currency": invoice.currency, "invoiced": Decimal("0"),
            "received": Decimal("0"), "balance": Decimal("0"),
        })
        row["invoiced"] += invoice.amount
        row["balance"] += invoice.balance
    for receipt in receipt_rows:
        if receipt.voided_at:
            continue
        row = totals.setdefault(receipt.currency, {
            "currency": receipt.currency, "invoiced": Decimal("0"),
            "received": Decimal("0"), "balance": Decimal("0"),
        })
        row["received"] += receipt.amount
    return list(totals.values())


def document_context(actor, *, invoice=None, receipt=None):
    from django.urls import reverse

    from apps.messaging.policies import may_access

    record = invoice or receipt
    staff = actor.is_staff_member
    payments_url = (reverse("staff:client_desk", args=[record.organization.slug, record.client_id])
                    + "?tab=invoices" if staff else reverse("organizations:client_invoices"))
    can_receive = bool(invoice and staff and invoice.published_at and not invoice.voided_at
                       and invoice.balance > 0 and may_access(
                           actor, invoice.organization, invoice.client, "subscriptions_approve"))
    return {
        "staff_desk": staff, "payments_url": payments_url,
        "record_payment_url": f"{payments_url}&receive={invoice.pk}#record-payment"
        if can_receive else "",
    }
