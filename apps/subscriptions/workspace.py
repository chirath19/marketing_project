"""Related project records, with recipient and feature access kept in domain selectors."""

from django.db.models import Q

from apps.analytics.selectors import client_reports
from apps.approvals.selectors import pending_for
from apps.core.features import visible
from apps.subscriptions import changes, invoices, receipts
from apps.subscriptions.guards import entitlements


def client_project(actor, subscription):
    organization = subscription.organization
    modules = entitlements(actor, organization=organization)
    module = next(
        (m for m in modules if m.key == subscription.service.category.workspace_module), None
    )
    reports = client_reports(actor, organization, actor).filter(subscription=subscription)
    invoice_links = Q(subscription=subscription)
    receipt_links = Q(subscription=subscription) | Q(invoice__subscription=subscription)
    if subscription.quote_id:
        invoice_links |= Q(quote_id=subscription.quote_id)
        receipt_links |= Q(invoice__quote_id=subscription.quote_id)
    return {
        "project_reports": reports,
        "latest_progress": reports.first(),
        "project_reviews": pending_for(actor, organization).filter(
            campaign__subscription=subscription
        ),
        "project_invoices": invoices.for_client(actor, organization, actor).filter(invoice_links),
        "project_receipts": receipts.for_client(actor, organization, actor).filter(receipt_links),
        "project_changes": changes.visible(actor, organization).filter(subscription=subscription)
        if visible("service_requests", actor)
        else [],
        "project_module": module if subscription.is_delivering else None,
    }


def staff_project(actor, subscription):
    from django.urls import reverse

    from apps.campaigns.selectors import for_organization
    from apps.core.workflow import staff_areas
    from apps.messaging.policies import may_access
    from apps.messaging.selectors import recipients

    contacts = []
    for member in recipients(actor).filter(organization=subscription.organization):
        permissions = {
            name: may_access(actor, member.organization, member.user, permission)
            for name, permission in [
                ("messages", "messaging_view"),
                ("reports", "analytics_view"),
                ("payments", "subscriptions_view"),
            ]
        }
        if any(permissions.values()):
            contacts.append(
                {
                    "name": member.user.get_full_name() or member.user.email,
                    "url": reverse(
                        "staff:client_desk", args=[member.organization.slug, member.user_id]
                    ),
                    **permissions,
                    "updates": client_reports(actor, member.organization, member.user).filter(
                        subscription=subscription
                    )[:2],
                }
            )
    tools = staff_areas(actor).get("projects", {}).get("items", [])
    module_key = subscription.service.category.workspace_module
    for item in tools:
        if item["key"] in {"seo", "paid_ads", "social", "email_marketing"}:
            item["href"] = reverse(
                "staff:" + item["key"] + "_workspace", args=[subscription.organization.slug]
            )
    return {
        "project_contacts": contacts,
        "project_campaigns": for_organization(actor, subscription.organization).filter(
            subscription=subscription
        ),
        "project_reviews": pending_for(actor, subscription.organization).filter(
            campaign__subscription=subscription
        ),
        "project_tools": [item for item in tools if item["key"] in {module_key, "campaigns"}],
    }
