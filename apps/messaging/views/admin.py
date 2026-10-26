from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.messaging import selectors
from apps.messaging.policies import may_access
from apps.messaging.views.workspace import _workspace
from apps.organizations import selectors as organizations
from apps.permissions.guards import require_staff_member
from apps.subscriptions.billing import document_context


@require_staff_member
def inbox(request):
    from apps.notifications.selectors import activity_summary

    unread = activity_summary(request.user)["message_threads"]
    recipients = [
        member
        for member in selectors.recipients(request.user)
        if any(
            may_access(request.user, member.organization, member.user, permission)
            for permission in ("messaging_view", "analytics_view", "subscriptions_view")
        )
    ]
    for member in recipients:
        member.unread_messages = unread.get(reverse("staff:client_desk", args=[
            member.organization.slug, member.user_id
        ]), 0)
    recipients.sort(key=lambda member: not bool(member.unread_messages))
    return render(
        request,
        "messaging/inbox.html",
        {
            "page_title": "Messages",
            "page_subtitle": "Choose a client to continue the conversation.",
            "nav_key": "messages",
            "recipients": recipients,
        },
    )


@require_staff_member
@require_http_methods(["GET", "POST"])
def workspace(request, slug, user_id):
    organization = organizations.get_organization(request.user, slug)
    if not organization:
        raise Http404
    client = selectors.recipient(request.user, organization, user_id)
    if not client:
        raise Http404
    default_tab = next(
        (
            tab
            for tab, permission in [
                ("messages", "messaging_view"),
                ("reports", "analytics_view"),
                ("receipts", "subscriptions_view"),
            ]
            if may_access(request.user, organization, client, permission)
        ),
        "messages",
    )
    tab = request.GET.get("tab", default_tab)
    return _workspace(request, organization, client, staff=True, tab=tab)


@require_staff_member
def receipt(request, pk):
    from apps.subscriptions import receipts

    record = receipts.get_receipt(request.user, pk)
    if record is None:
        raise Http404
    return render(request, "messaging/receipt.html", {
        "receipt": record, **document_context(request.user, receipt=record),
    })


@require_staff_member
def invoice(request, pk):
    from apps.subscriptions.invoices import get_invoice

    record = get_invoice(request.user, pk)
    if not record:
        raise Http404
    return render(request, "messaging/invoice.html", {
        "invoice": record, **document_context(request.user, invoice=record),
    })
