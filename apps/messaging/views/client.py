from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.messaging.views.workspace import _workspace
from apps.subscriptions import receipts
from apps.subscriptions.billing import document_context


@login_required
@require_http_methods(["GET", "POST"])
def workspace(request, tab="messages"):
    if not request.user.is_client:
        raise Http404
    if not request.organization:
        return redirect("organizations:setup")
    return _workspace(request, request.organization, request.user, tab=tab)


@login_required
def receipt(request, pk):
    if not request.user.is_client:
        raise Http404
    record = receipts.get_receipt(request.user, pk, request.organization)
    if record is None:
        raise Http404
    return render(request, "messaging/receipt.html", {
        "receipt": record, **document_context(request.user, receipt=record),
    })


@login_required
def invoice(request, pk):
    from apps.subscriptions.invoices import get_invoice

    if not request.user.is_client:
        raise Http404
    record = get_invoice(request.user, pk, request.organization)
    if not record:
        raise Http404
    return render(request, "messaging/invoice.html", {
        "invoice": record, **document_context(request.user, invoice=record),
    })


@login_required
def report_attachment(request, pk):
    from django.http import HttpResponse
    from django.utils.http import content_disposition_header

    from apps.analytics.selectors import attachment_for

    attachment = attachment_for(request.user, pk, request.organization)
    if not attachment:
        raise Http404
    response = HttpResponse(bytes(attachment.data), content_type=attachment.content_type)
    response["Content-Disposition"] = content_disposition_header(True, attachment.name)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
