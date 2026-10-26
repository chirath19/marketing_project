"""Manual billing records. An invoice or receipt never initiates a payment."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.messaging.policies import may_access
from apps.messaging.references import validate
from apps.notifications.services import notify
from apps.subscriptions.billing import prepare_document
from apps.subscriptions.models import Invoice


def for_client(actor, organization, client):
    rows = Invoice.objects.filter(organization=organization, client=client)
    if not may_access(actor, organization, client, "subscriptions_view"):
        return rows.none()
    if not actor.is_staff_member:
        rows = rows.filter(published_at__isnull=False)
    return rows.select_related("client", "organization", "subscription", "quote").prefetch_related(
        "receipts"
    )


def _authorize(actor, invoice):
    if not actor.is_staff_member or not may_access(
        actor, invoice.organization, invoice.client, "subscriptions_approve"
    ):
        raise PermissionDenied


@transaction.atomic
def create(*, actor, organization, client, publish=False, **values):
    invoice = Invoice(organization=organization, client=client, created_by=actor, **values)
    _authorize(actor, invoice)
    validate(
        actor=actor,
        organization=organization,
        client=client,
        subscription=invoice.subscription,
        quote=invoice.quote,
    )
    previous = prepare_document(invoice, "INV")
    if previous:
        return previous
    invoice.currency = invoice.currency.upper()
    if publish:
        invoice.published_at = timezone.now()
    invoice.full_clean()
    invoice.save()
    if publish:
        _notify(invoice)
    return invoice


@transaction.atomic
def update_draft(*, actor, invoice, publish=False, **values):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    _authorize(actor, invoice)
    if invoice.published_at or invoice.voided_at:
        raise ValidationError(
            "Only a draft invoice can be edited. Void an issued invoice to correct it."
        )
    for name in ("description", "amount", "currency", "issued_on", "due_on",
                 "subscription", "quote"):
        if name in values:
            setattr(invoice, name, values[name])
    validate(actor=actor, organization=invoice.organization, client=invoice.client,
             subscription=invoice.subscription, quote=invoice.quote)
    invoice.currency = invoice.currency.upper()
    if publish:
        invoice.published_at = timezone.now()
    invoice.full_clean()
    invoice.save()
    if publish:
        _notify(invoice)
    return invoice


@transaction.atomic
def publish(*, actor, invoice):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    _authorize(actor, invoice)
    if invoice.voided_at:
        raise ValidationError("A voided invoice cannot be published.")
    if not invoice.published_at:
        invoice.published_at = timezone.now()
        invoice.save(update_fields=["published_at", "updated_at"])
        _notify(invoice)
    return invoice


@transaction.atomic
def void(*, actor, invoice, reason):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    _authorize(actor, invoice)
    if invoice.paid_amount:
        raise ValidationError("Correct linked receipts before voiding this invoice.")
    if not reason.strip() or len(reason) > 300:
        raise ValidationError("Give a correction reason of 1–300 characters.")
    if not invoice.voided_at:
        invoice.voided_at, invoice.void_reason = timezone.now(), reason.strip()
        invoice.save(update_fields=["voided_at", "void_reason", "updated_at"])
        if invoice.published_at:
            _notify(invoice)
    return invoice


def _notify(invoice):
    notify(
        recipient=invoice.client,
        title=f"Invoice {invoice.reference}: {invoice.payment_status}",
        url=reverse("organizations:client_invoices"),
        category="payments",
    )


def get_invoice(actor, pk, organization=None):
    invoice = (
        Invoice.objects.select_related("organization", "client", "subscription", "quote")
        .filter(pk=pk)
        .first()
    )
    if invoice and (
        actor.is_staff_member or getattr(organization, "pk", None) == invoice.organization_id
    ):
        return for_client(actor, invoice.organization, invoice.client).filter(pk=pk).first()
    return None
