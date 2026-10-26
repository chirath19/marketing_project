from datetime import timedelta
from uuid import uuid4

from django import forms
from django.utils import timezone

from apps.core.forms import StyledForm


class MessageForm(StyledForm):
    body = forms.CharField(
        max_length=5000, label="Message", widget=forms.Textarea(attrs={"rows": 4})
    )


class ReportForm(StyledForm):
    title = forms.CharField(max_length=200)
    summary = forms.CharField(max_length=12000, widget=forms.Textarea(attrs={"rows": 5}))
    next_steps = forms.CharField(
        max_length=5000, required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    progress = forms.IntegerField(min_value=0, max_value=100, initial=0, label="Progress (%)")
    status = forms.ChoiceField(
        choices=[
            ("planned", "Planned"),
            ("in_progress", "In progress"),
            ("waiting", "Waiting on client"),
            ("completed", "Completed"),
        ]
    )
    publish = forms.BooleanField(required=False, label="Publish to this client now")


class BillingForm(StyledForm):
    submission_key = forms.UUIDField(required=False, initial=uuid4, widget=forms.HiddenInput)


class ReceiptForm(BillingForm):
    description = forms.CharField(max_length=300)
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    currency = forms.CharField(max_length=3, min_length=3, initial="USD")
    paid_on = forms.DateField(initial=timezone.localdate,
                              widget=forms.DateInput(attrs={"type": "date"}))
    payment_method = forms.CharField(max_length=100, help_text="For example bank transfer or cash.")
    notes = forms.CharField(
        max_length=3000, required=False, widget=forms.Textarea(attrs={"rows": 3})
    )


class InvoiceForm(BillingForm):
    description = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 3}))
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    currency = forms.RegexField(r"^[A-Za-z]{3}$", initial="USD", max_length=3)
    issued_on = forms.DateField(initial=timezone.localdate,
                                widget=forms.DateInput(attrs={"type": "date"}))
    due_on = forms.DateField(initial=lambda: timezone.localdate() + timedelta(days=14),
                            widget=forms.DateInput(attrs={"type": "date"}))
    publish = forms.BooleanField(required=False, label="Publish this invoice to the client")


class InvoiceChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.reference} · {obj.currency} {obj.balance:,.2f} remaining"


class ClientContextMixin:
    def __init__(self, *args, actor=None, organization=None, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.leads.models import QuoteRequest
        from apps.leads.selectors import quotes_for_client
        from apps.permissions.access import can
        from apps.subscriptions.models import ClientSubscription, Invoice

        subscriptions = ClientSubscription.objects.none()
        quotes = QuoteRequest.objects.none()
        invoices = Invoice.objects.none()
        if organization and client:
            subscriptions = ClientSubscription.objects.filter(organization=organization)
            if not actor.is_staff_member or can(actor, "quotes_view", organization):
                quotes = quotes_for_client(client).filter(organization=organization)
            invoices = Invoice.objects.filter(
                organization=organization,
                client=client,
                published_at__isnull=False,
                voided_at__isnull=True,
            )
        self.fields["subscription"] = forms.ModelChoiceField(
            queryset=subscriptions, required=False, label="Related service"
        )
        if self.include_quote:
            self.fields["quote"] = forms.ModelChoiceField(
                queryset=quotes, required=False, label="Related quotation"
            )
        if self.include_invoice:
            self.fields["invoice"] = InvoiceChoiceField(
                queryset=invoices.prefetch_related("receipts"), required=False,
                label="Invoice being paid", empty_label="Other payment / no invoice"
            )

    include_quote = False
    include_invoice = False


class LinkedMessageForm(ClientContextMixin, MessageForm):
    include_quote = True


class LinkedReportForm(ClientContextMixin, ReportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attachment"].widget.attrs["class"] = "ui-input"

    milestones = forms.CharField(
        max_length=5000, required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    completed_work = forms.CharField(
        max_length=5000, required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    attachment = forms.FileField(
        required=False, help_text="PDF, PNG or JPEG; up to 5 MB. Private to this report."
    )


class LinkedReceiptForm(ClientContextMixin, ReceiptForm):
    include_invoice = True

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        if invoice:
            self.initial.update({
                "invoice": invoice.pk, "subscription": invoice.subscription_id,
                "currency": invoice.currency, "amount": invoice.balance,
                "description": f"Payment for {invoice.reference}",
            })
            for name in ("invoice", "subscription", "currency"):
                self.fields[name].disabled = True


class LinkedInvoiceForm(ClientContextMixin, InvoiceForm):
    include_quote = True
