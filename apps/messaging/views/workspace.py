"""Shared presentation for staff and client communication desks."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render

from apps.analytics import selectors as reports
from apps.analytics import services as reporting
from apps.messaging import selectors, services
from apps.messaging.forms import LinkedInvoiceForm as InvoiceForm
from apps.messaging.forms import LinkedMessageForm as MessageForm
from apps.messaging.forms import LinkedReceiptForm as ReceiptForm
from apps.messaging.forms import LinkedReportForm as ReportForm
from apps.messaging.policies import may_access
from apps.messaging.presentation import group
from apps.subscriptions import billing, invoices, receipts


def _workspace(request, organization, client, *, staff=False, tab="messages"):
    if tab not in {"messages", "reports", "receipts", "invoices"}:
        raise Http404
    permissions = {
        "messages": "messaging_view",
        "reports": "analytics_view",
        "receipts": "subscriptions_view",
        "invoices": "subscriptions_view",
    }
    if not may_access(request.user, organization, client, permissions[tab]):
        raise Http404
    context = {"actor": request.user, "organization": organization, "client": client}
    message_form, report_form, receipt_form = (
        MessageForm(**context),
        ReportForm(**context),
        ReceiptForm(**context),
    )
    invoice_form = InvoiceForm(**context)
    project = None
    project_id = request.GET.get("project", "")
    if project_id:
        project = (
            message_form.fields["subscription"]
            .queryset.filter(pk=project_id if project_id.isdigit() else 0)
            .first()
        )
        if project is None:
            raise Http404
        for form in (message_form, report_form, receipt_form, invoice_form):
            form.initial["subscription"] = project.pk
    selected_invoice = None
    editing_invoice = None
    if staff and tab in {"invoices", "receipts"}:
        invoice_id = request.GET.get("receive") or request.GET.get("edit_invoice")
        if invoice_id:
            if not may_access(request.user, organization, client, "subscriptions_approve"):
                raise PermissionDenied
            record = invoices.for_client(request.user, organization, client).filter(
                pk=invoice_id if invoice_id.isdigit() else 0,
            ).first()
            if record is None or record.voided_at:
                raise Http404
            if request.GET.get("receive"):
                if not record.published_at:
                    raise Http404
                selected_invoice = record
                receipt_form = ReceiptForm(invoice=record, **context)
            else:
                if record.published_at:
                    raise Http404
                editing_invoice = record
                invoice_form = InvoiceForm(initial={
                    field: getattr(record, field)
                    for field in ("description", "amount", "currency", "issued_on", "due_on",
                                  "quote", "subscription")
                }, **context)
    editing_report = None
    edit_id = request.GET.get("edit", "")
    if staff and tab == "reports" and edit_id:
        editing_report = (
            reports.client_reports(request.user, organization, client)
            .filter(pk=edit_id if edit_id.isdigit() else 0)
            .first()
        )
        if not editing_report or not may_access(
            request.user, organization, client, "analytics_edit"
        ):
            raise Http404
        report_form = ReportForm(
            initial={
                key: getattr(editing_report, key)
                for key in (
                    "title",
                    "summary",
                    "next_steps",
                    "progress",
                    "status",
                    "subscription",
                    "milestones",
                    "completed_work",
                )
            },
            **context,
        )
    if request.method == "POST":
        action = request.POST.get("action", "message")
        try:
            if action == "message":
                message_form = MessageForm(request.POST, **context)
                if message_form.is_valid():
                    services.send(
                        actor=request.user,
                        organization=organization,
                        client=client,
                        **message_form.cleaned_data,
                    )
                    return redirect(request.path + "?tab=messages")
            elif staff and action in {"report", "update_report"}:
                report_form = ReportForm(request.POST, request.FILES, **context)
                if report_form.is_valid():
                    if action == "update_report":
                        if not editing_report:
                            raise Http404
                        reporting.update_report(
                            actor=request.user, report=editing_report, **report_form.cleaned_data
                        )
                    else:
                        reporting.create_report(
                            actor=request.user,
                            organization=organization,
                            client=client,
                            **report_form.cleaned_data,
                        )
                    messages.success(request, "Progress report saved.")
                    return redirect(request.path + "?tab=reports")
            elif staff and action == "receipt":
                receipt_form = ReceiptForm(request.POST, invoice=selected_invoice, **context)
                if receipt_form.is_valid():
                    receipts.issue(
                        actor=request.user,
                        organization=organization,
                        client=client,
                        **receipt_form.cleaned_data,
                    )
                    messages.success(request, "Payment receipt issued to this client.")
                    return redirect(request.path + "?tab=invoices#payment-history")
            elif staff and action in {"invoice", "update_invoice"}:
                invoice_form = InvoiceForm(request.POST, **context)
                if invoice_form.is_valid():
                    if action == "update_invoice":
                        if not editing_invoice:
                            raise Http404
                        invoices.update_draft(actor=request.user, invoice=editing_invoice,
                                              **invoice_form.cleaned_data)
                    else:
                        invoices.create(
                            actor=request.user, organization=organization, client=client,
                            **invoice_form.cleaned_data,
                        )
                    messages.success(request, "Invoice saved.")
                    return redirect(request.path + "?tab=invoices")
            elif staff and action in {"publish_invoice", "void_invoice"}:
                record_id = request.POST.get("record", "")
                invoice = (
                    invoices.for_client(request.user, organization, client)
                    .filter(pk=record_id if record_id.isdigit() else 0)
                    .first()
                )
                if not invoice:
                    raise Http404
                if action == "publish_invoice":
                    invoices.publish(actor=request.user, invoice=invoice)
                else:
                    invoices.void(
                        actor=request.user, invoice=invoice, reason=request.POST.get("reason", "")
                    )
                return redirect(request.get_full_path())
            elif staff and action == "attachment":
                record_id = request.POST.get("record", "")
                report = (
                    reports.client_reports(request.user, organization, client)
                    .filter(pk=record_id if record_id.isdigit() else 0)
                    .first()
                )
                if not report:
                    raise Http404
                upload = request.FILES.get("attachment")
                if not upload:
                    raise ValidationError("Choose an attachment.")
                reporting.add_attachment(actor=request.user, report=report, upload=upload)
                return redirect(request.get_full_path())
            elif staff and action == "publish":
                report = (
                    reports.client_reports(request.user, organization, client)
                    .filter(
                        pk=request.POST.get("record")
                        if request.POST.get("record", "").isdigit()
                        else 0
                    )
                    .first()
                )
                if report is None:
                    raise Http404
                reporting.publish_report(actor=request.user, report=report)
                return redirect(request.get_full_path())
            elif staff and action == "void":
                receipt = (
                    receipts.for_client(request.user, organization, client)
                    .filter(
                        pk=request.POST.get("record")
                        if request.POST.get("record", "").isdigit()
                        else 0
                    )
                    .first()
                )
                if receipt is None:
                    raise Http404
                receipts.void(
                    actor=request.user, receipt=receipt, reason=request.POST.get("reason", "")
                )
                return redirect(request.get_full_path())
            else:
                raise PermissionDenied
        except ValidationError as exc:
            if action == "receipt":
                receipt_form.add_error(None, "; ".join(exc.messages))
            elif action in {"invoice", "update_invoice"}:
                invoice_form.add_error(None, "; ".join(exc.messages))
            else:
                messages.error(request, "; ".join(exc.messages))
    thread = selectors.conversation(request.user, organization, client)
    new_message_ids = set()
    if thread and tab == "messages":
        incoming = thread.messages.filter(read_at__isnull=True)
        incoming = (
            incoming.filter(sender=client) if staff else incoming.exclude(sender=request.user)
        )
        new_message_ids = set(incoming.values_list("pk", flat=True))
        services.mark_read(actor=request.user, conversation=thread)
    message_page = Paginator(
        thread.messages.select_related("sender", "quote", "subscription").order_by(
            "-created_at", "-pk"
        )
        if thread
        else [],
        50,
    ).get_page(request.GET.get("page", 1))
    # The page is fetched newest first so page 1 is the latest 50; the chat
    # reads top to bottom, so it is shown oldest first.
    chat_messages = list(reversed(message_page.object_list))
    for message in chat_messages:
        message.was_unread = message.pk in new_message_ids
        message.outgoing = (message.sender.is_staff_member if staff
                            else message.sender_id == request.user.pk)
        message.has_receipt = True
    group(chat_messages)
    payment_invoices = list(invoices.for_client(request.user, organization, client)) if tab in {
        "invoices", "receipts"
    } else []
    payment_receipts = list(receipts.for_client(request.user, organization, client)) if tab in {
        "invoices", "receipts"
    } else []
    return render(
        request,
        "messaging/workspace.html",
        {
            "shell": "admin/base.html" if staff else "portal/base.html",
            "staff_desk": staff,
            "organization": organization,
            "client": client,
            "tab": tab,
            "page_title": client.get_full_name() or client.email,
            "page_subtitle": f"{organization.label} · Client workspace",
            "nav_key": "payments"
            if tab in {"receipts", "invoices"}
            else "projects"
            if tab == "reports"
            else "messages",
            "project": project,
            "desk_heading": {
                "messages": "Messages",
                "reports": "Progress updates & files",
                "receipts": "Payments",
                "invoices": "Payments",
            }[tab],
            "portal_key": {
                "messages": "messages",
                "reports": "reports",
                "receipts": "receipts",
                "invoices": "invoices",
            }[tab],
            "chat_messages": chat_messages,
            "message_page": message_page,
            "reports": reports.client_reports(request.user, organization, client)
            if tab == "reports"
            else [],
            "receipts": payment_receipts,
            "invoice_form": invoice_form,
            "invoices": payment_invoices,
            "payment_summary": billing.summary(payment_invoices, payment_receipts),
            "selected_invoice": selected_invoice,
            "editing_invoice": editing_invoice,
            "record_payment": request.GET.get("record_payment") == "1",
            "message_form": message_form,
            "report_form": report_form,
            "editing_report": editing_report,
            "receipt_form": receipt_form,
            "can_message": may_access(request.user, organization, client, "messaging_create"),
            "can_report": staff
            and may_access(request.user, organization, client, "analytics_create"),
            "can_publish": staff
            and may_access(request.user, organization, client, "analytics_edit"),
            "can_receipt": staff
            and may_access(request.user, organization, client, "subscriptions_approve"),
            "show_messages": may_access(request.user, organization, client, "messaging_view"),
            "show_reports": may_access(request.user, organization, client, "analytics_view"),
            "show_receipts": may_access(request.user, organization, client, "subscriptions_view"),
        },
    )
