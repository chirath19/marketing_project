from django.urls import path

from apps.approvals.views import client as approval_client
from apps.campaigns.views import client as campaign_client
from apps.email_marketing.views import client as email_client
from apps.leads.views import client as quote_client
from apps.messaging.views import client as messaging_client
from apps.organizations import views
from apps.social.views import client as social_client
from apps.subscriptions.views import changes as service_changes
from apps.subscriptions.views import client as service_client

app_name = "organizations"

urlpatterns = [
    path("service-requests/", service_changes.client_list, name="service_requests"),
    path(
        "services/<int:pk>/request-change/",
        service_changes.client_create,
        name="service_change_create",
    ),
    path("invoices/", messaging_client.workspace, {"tab": "invoices"}, name="client_invoices"),
    path("invoices/<int:pk>/", messaging_client.invoice, name="invoice"),
    path(
        "reports/attachments/<int:pk>/",
        messaging_client.report_attachment,
        name="report_attachment",
    ),
    path("messages/", messaging_client.workspace, name="client_desk"),
    path("reports/", messaging_client.workspace, {"tab": "reports"}, name="client_reports"),
    path("receipts/", messaging_client.workspace, {"tab": "receipts"}, name="client_receipts"),
    path("receipts/<int:pk>/", messaging_client.receipt, name="payment_receipt"),
    path("quotes/new/", quote_client.quote_create, name="quote_create"),
    path("approvals/<uuid:pk>/", approval_client.detail, name="approval_detail"),
    path("approvals/<uuid:pk>/decide/", approval_client.decide, name="approval_decide"),
    path("approvals/<uuid:pk>/comment/", approval_client.comment, name="approval_comment"),
    path("email-marketing/work/<uuid:pk>/", email_client.detail, name="email_marketing_detail"),
    path("email-marketing/reviews/<uuid:pk>/", email_client.review, name="email_marketing_review"),
    path("social/content/<uuid:pk>/", social_client.detail, name="social_detail"),
    path("social/reviews/<uuid:pk>/", social_client.review, name="social_review"),
    path("setup/", views.setup, name="setup"),
    path("", views.overview, name="overview"),
    path("settings/", views.settings_view, name="settings"),
    path("members/", views.members, name="members"),
    path("members/<int:member_id>/role/", views.change_member_role, name="change_role"),
    path("members/<int:member_id>/remove/", views.remove_member, name="remove_member"),
    path("switch/", views.switch, name="switch"),
    # Quote requests, owned by apps.leads and mounted here because this
    # is where the client looks for them. The same arrangement the staff
    # dashboard uses for the Inbox and the lead pipeline.
    path("quotes/", quote_client.quote_list, name="quotes"),
    path("quotes/<int:pk>/", quote_client.quote_detail, name="quote_detail"),
    path("quotes/<int:pk>/reply/", quote_client.quote_reply, name="quote_reply"),
    path("quotes/<int:pk>/decision/", quote_client.quote_decision, name="quote_decision"),
    # Services, owned by apps.subscriptions and mounted here for the
    # same reason the quotes are.
    path("services/", service_client.service_list, name="services"),
    path("services/<int:pk>/", service_client.service_detail, name="service_detail"),
    # The delivery modules. One route, one view: each module declares
    # what it is in apps/core/modules.py, and the view checks the
    # client is entitled to the one they asked for.
    path("area/<slug:key>/", views.module_page, name="portal_module"),
    path("campaigns/<int:pk>/", campaign_client.campaign_detail, name="campaign_detail"),
]
