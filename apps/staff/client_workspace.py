"""Compose a client workspace using each domain's scoped read contract."""

from django.core.paginator import Paginator
from django.urls import reverse

from apps.analytics.selectors import client_reports
from apps.approvals.selectors import pending_for
from apps.leads.selectors import quote_requests
from apps.messaging.policies import may_access
from apps.subscriptions import invoices, receipts


def context_for(actor, organization, members, selected_id=None, quote_page=None):
    members = list(members)
    selected = next((m.user for m in members if str(m.user_id) == str(selected_id)), None)
    if selected_id and selected is None:
        from django.http import Http404

        raise Http404
    if selected is None and members:
        selected = next((m.user for m in members if m.role == "owner"), members[0].user)
    quotes_page = Paginator(quote_requests(actor).filter(organization=organization), 12).get_page(
        quote_page
    )
    data = {
        "workspace_quotes": quotes_page,
        "workspace_reviews": pending_for(actor, organization),
        "selected_client": selected,
        "selected_client_label": (selected.get_full_name() or selected.email)
        if selected
        else "No active client contact",
    }
    if selected:
        data.update(
            {
                "desk_url": reverse("staff:client_desk", args=[organization.slug, selected.pk]),
                "workspace_reports": client_reports(actor, organization, selected)[:5],
                "workspace_invoices": invoices.for_client(actor, organization, selected)[:5],
                "workspace_receipts": receipts.for_client(actor, organization, selected)[:5],
                "desk_messages": may_access(actor, organization, selected, "messaging_view"),
                "desk_reports": may_access(actor, organization, selected, "analytics_view"),
                "desk_payments": may_access(actor, organization, selected, "subscriptions_view"),
            }
        )
    return data
