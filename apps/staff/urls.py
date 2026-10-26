from django.urls import path

from apps.approvals.views import admin as approval_admin
from apps.campaigns.views import admin as campaign_admin
from apps.catalog.views import admin as catalog_admin
from apps.cms.views import admin as cms_admin
from apps.cms.views import blog_admin, copy_admin
from apps.email_marketing.views import admin as email_admin
from apps.integrations.views import admin as integrations_admin
from apps.leads.views import admin as leads_admin
from apps.leads.views import quotes as quote_admin
from apps.messaging.views import admin as messaging_admin
from apps.paid_ads.views import admin as paid_ads_admin
from apps.seo.views import admin as seo_admin
from apps.social.views import admin as social_admin
from apps.staff import views
from apps.staff.views import clients, modules, operating, roles, staff_admin, workflow
from apps.subscriptions.views import admin as subscription_admin
from apps.subscriptions.views import changes as service_changes

app_name = "staff"

urlpatterns = [
    path("workspace/<slug:area>/", workflow.workspace, name="workflow"),
    path("service-requests/", service_changes.staff_list, name="service_requests"),
    path(
        "service-requests/<int:pk>/apply/",
        service_changes.staff_apply,
        name="service_request_apply",
    ),
    path("invoices/<int:pk>/", messaging_admin.invoice, name="invoice"),
    path("team/<int:pk>/remove/", staff_admin.staff_remove, name="staff_remove"),
    path("registrations/", clients.registrations, name="registrations"),
    path(
        "registrations/<int:user_id>/approve/",
        clients.approve_registration,
        name="registration_approve",
    ),
    path("messages/", messaging_admin.inbox, name="module_messages"),
    path(
        "clients/<slug:slug>/workspace/<int:user_id>/",
        messaging_admin.workspace,
        name="client_desk",
    ),
    path("receipts/<int:pk>/", messaging_admin.receipt, name="payment_receipt"),
    # Shell
    path("dashboard/", views.dashboard, name="dashboard"),
    path("search/", views.search, name="search"),
    # Staff administration
    path("", views.staff_list, name="list"),
    path("new/", views.staff_create, name="create"),
    path("<int:pk>/", views.staff_detail, name="detail"),
    path("<int:pk>/update/", views.staff_update, name="update"),
    path("<int:pk>/roles/", views.staff_set_roles, name="set_roles"),
    path("<int:pk>/active/", views.staff_set_active, name="set_active"),
    path("<int:pk>/override/", staff_admin.staff_override, name="staff_override"),
    # Client assignments
    path("<int:pk>/assign/", views.assign_client, name="assign_client"),
    path(
        "assignments/<int:assignment_id>/end/", views.end_client_assignment, name="end_assignment"
    ),
    # Staff-side client views and downloads
    path("clients/", views.client_list, name="clients"),
    path("clients/export/", views.export_clients, name="export_clients"),
    path("clients/<slug:slug>/", views.client_detail, name="client_detail"),
    path("clients/<slug:slug>/export/", views.export_client, name="export_client"),
    # Roles
    path("roles/", views.role_list, name="roles"),
    path("roles/new/", roles.role_create, name="role_create"),
    path("roles/<int:pk>/edit/", roles.role_edit, name="role_edit"),
    path("roles/<int:pk>/delete/", roles.role_delete, name="role_delete"),
    path("roles/<int:pk>/", views.role_detail, name="role_detail"),
    path("roles/<int:pk>/permissions/", views.role_set_permissions, name="role_set_permissions"),
    # Sections whose module is not built yet. Real routes, real guards,
    # honest placeholder pages — see apps/staff/views/modules.py.
    # Leads, the Inbox and quote requests, built by apps.leads.
    path("leads/", leads_admin.lead_list, name="module_leads"),
    path("leads/<int:pk>/", leads_admin.lead_detail, name="lead_detail"),
    path("leads/<int:pk>/note/", leads_admin.lead_note, name="lead_note"),
    path("leads/<int:pk>/status/", leads_admin.lead_status, name="lead_status"),
    path("leads/<int:pk>/assign/", leads_admin.lead_assign, name="lead_assign"),
    path("leads/<int:pk>/details/", leads_admin.lead_details, name="lead_details"),
    # Quote requests: the pipeline is the module's home page, and the
    # raw submissions stay reachable through the Inbox.
    path("quotes/", quote_admin.quote_list, name="module_quotes"),
    path("quotes/submissions/", leads_admin.quote_inbox, name="quote_inbox"),
    path("quotes/<int:pk>/", quote_admin.quote_detail, name="quote_detail"),
    path("quotes/<int:pk>/status/", quote_admin.quote_status, name="quote_status"),
    path("quotes/<int:pk>/assign/", quote_admin.quote_assign, name="quote_assign"),
    path("quotes/<int:pk>/note/", quote_admin.quote_note, name="quote_note"),
    path("quotes/<int:pk>/reply/", quote_admin.quote_reply, name="quote_reply"),
    path("quotes/<int:pk>/lines/new/", quote_admin.quote_add_line, name="quote_add_line"),
    path("quotes/<int:pk>/scope/", quote_admin.quote_scope, name="quote_scope"),
    path("quotes/<int:pk>/client/", quote_admin.quote_organization, name="quote_organization"),
    # Client services, built by apps.subscriptions.
    path("subscriptions/", subscription_admin.subscription_list, name="module_subscriptions"),
    path(
        "subscriptions/<int:pk>/",
        subscription_admin.subscription_detail,
        name="subscription_detail",
    ),
    path(
        "subscriptions/<int:pk>/update/",
        subscription_admin.subscription_update,
        name="subscription_update",
    ),
    path(
        "subscriptions/<int:pk>/status/",
        subscription_admin.subscription_status,
        name="subscription_status",
    ),
    path(
        "subscriptions/<int:pk>/note/",
        subscription_admin.subscription_note,
        name="subscription_note",
    ),
    path(
        "clients/<slug:slug>/services/new/",
        subscription_admin.subscription_create,
        name="subscription_create",
    ),
    path(
        "quotes/<int:pk>/to-services/",
        subscription_admin.subscription_from_quote,
        name="subscription_from_quote",
    ),
    path("approvals/", approval_admin.inbox, name="module_approvals"),
    path("approvals/new/<slug:slug>/", approval_admin.create, name="approval_create"),
    path("approvals/<uuid:pk>/", approval_admin.detail, name="approval_detail"),
    path("approvals/<uuid:pk>/comment/", approval_admin.comment, name="approval_comment"),
    path("approvals/<uuid:pk>/cancel/", approval_admin.cancel, name="approval_cancel"),
    # Campaigns across every service, built by apps.campaigns.
    path("campaigns/", campaign_admin.campaign_list, name="module_campaigns"),
    path("campaigns/<int:pk>/", campaign_admin.campaign_detail, name="campaign_detail"),
    path("campaigns/<int:pk>/update/", campaign_admin.campaign_update, name="campaign_update"),
    path(
        "campaigns/<int:pk>/detail-fields/",
        campaign_admin.campaign_detail_update,
        name="campaign_detail_update",
    ),
    path(
        "campaigns/<int:pk>/map/",
        campaign_admin.campaign_map_external,
        name="campaign_map_external",
    ),
    path("campaigns/<int:pk>/status/", campaign_admin.campaign_status, name="campaign_status"),
    path("campaigns/<int:pk>/assign/", campaign_admin.campaign_assign, name="campaign_assign"),
    path("campaigns/<int:pk>/note/", campaign_admin.campaign_note, name="campaign_note"),
    path(
        "clients/<slug:slug>/campaigns/new/", campaign_admin.campaign_create, name="campaign_create"
    ),
    # The SEO workspace, built by apps.seo. Per client, because SEO work
    # is only meaningful against one site.
    path("seo/", seo_admin.seo_home, name="module_seo"),
    path("seo/<slug:slug>/", seo_admin.client_workspace, name="seo_workspace"),
    path("seo/<slug:slug>/audits/", seo_admin.audit_list, name="seo_audits"),
    path("seo/<slug:slug>/audits/new/", seo_admin.audit_create, name="seo_audit_create"),
    path("seo/audits/<int:pk>/", seo_admin.audit_detail, name="seo_audit_detail"),
    path("seo/audits/<int:pk>/update/", seo_admin.audit_update, name="seo_audit_update"),
    path("seo/audits/<int:pk>/deliver/", seo_admin.audit_deliver, name="seo_audit_deliver"),
    path("seo/audits/<int:pk>/issues/new/", seo_admin.issue_create, name="seo_issue_create"),
    path("seo/issues/<int:pk>/status/", seo_admin.issue_status, name="seo_issue_status"),
    path("seo/<slug:slug>/keywords/", seo_admin.keyword_list, name="seo_keywords"),
    path("seo/<slug:slug>/keywords/new/", seo_admin.keyword_create, name="seo_keyword_create"),
    path("seo/<slug:slug>/keywords/import/", seo_admin.keyword_import, name="seo_keyword_import"),
    path("seo/keywords/<int:pk>/", seo_admin.keyword_detail, name="seo_keyword_detail"),
    path("seo/keywords/<int:pk>/position/", seo_admin.position_record, name="seo_position_record"),
    path("seo/<slug:slug>/tasks/", seo_admin.task_list, name="seo_tasks"),
    path("seo/<slug:slug>/tasks/new/", seo_admin.task_create, name="seo_task_create"),
    path("seo/tasks/<int:pk>/update/", seo_admin.task_update, name="seo_task_update"),
    path("seo/<slug:slug>/links/", seo_admin.backlink_list, name="seo_backlinks"),
    path("seo/<slug:slug>/links/new/", seo_admin.backlink_create, name="seo_backlink_create"),
    path("seo/links/<int:pk>/update/", seo_admin.backlink_update, name="seo_backlink_update"),
    path("paid-ads/", paid_ads_admin.home, name="module_paid_ads"),
    path("paid-ads/<slug:slug>/", paid_ads_admin.workspace, name="paid_ads_workspace"),
    path("paid-ads/<slug:slug>/record/", paid_ads_admin.record, name="paid_ads_record"),
    path("paid-ads/<slug:slug>/import/", paid_ads_admin.import_data, name="paid_ads_import"),
    path("paid-ads/<slug:slug>/goals/", paid_ads_admin.goals, name="paid_ads_goals"),
    path(
        "paid-ads/<slug:slug>/goals/new/", paid_ads_admin.goal_create, name="paid_ads_goal_create"
    ),
    path(
        "paid-ads/<slug:slug>/goals/<int:pk>/", paid_ads_admin.goal_edit, name="paid_ads_goal_edit"
    ),
    path("social/", social_admin.home, name="module_social"),
    path("social/<slug:slug>/", social_admin.workspace, name="social_workspace"),
    path("social/<slug:slug>/new/<slug:kind>/", social_admin.create, name="social_create"),
    path("social/<slug:slug>/edit/<slug:kind>/<str:pk>/", social_admin.edit, name="social_edit"),
    path("social/<slug:slug>/content/<uuid:pk>/", social_admin.detail, name="social_detail"),
    path("social/<slug:slug>/content/<uuid:pk>/status/", social_admin.status, name="social_status"),
    path(
        "social/<slug:slug>/content/<uuid:pk>/metrics/", social_admin.metrics, name="social_metrics"
    ),
    path(
        "social/<slug:slug>/content/<uuid:pk>/deliverables/new/",
        social_admin.deliverable_create,
        name="social_deliverable_create",
    ),
    path(
        "social/<slug:slug>/content/<uuid:pk>/deliverables/<uuid:delivery_id>/",
        social_admin.deliverable_edit,
        name="social_deliverable_edit",
    ),
    path(
        "social/<slug:slug>/content/<uuid:pk>/deliverables/<uuid:delivery_id>/review/",
        social_admin.request_review,
        name="social_request_review",
    ),
    path("email-marketing/", email_admin.home, name="module_email_marketing"),
    path("email-marketing/<slug:slug>/", email_admin.workspace, name="email_marketing_workspace"),
    path("email-marketing/<slug:slug>/new/", email_admin.create, name="email_marketing_create"),
    path(
        "email-marketing/<slug:slug>/work/<uuid:pk>/",
        email_admin.detail,
        name="email_marketing_detail",
    ),
    path(
        "email-marketing/<slug:slug>/work/<uuid:pk>/edit/",
        email_admin.edit,
        name="email_marketing_edit",
    ),
    path(
        "email-marketing/<slug:slug>/work/<uuid:pk>/status/",
        email_admin.status,
        name="email_marketing_status",
    ),
    path(
        "email-marketing/<slug:slug>/work/<uuid:pk>/metrics/",
        email_admin.metrics,
        name="email_marketing_metrics",
    ),
    path(
        "email-marketing/<slug:slug>/work/<uuid:pk>/deliverables/new/",
        email_admin.deliverable_create,
        name="email_marketing_deliverable_create",
    ),
    path(
        "email-marketing/<slug:slug>/work/<uuid:pk>/deliverables/<uuid:delivery_id>/",
        email_admin.deliverable_edit,
        name="email_marketing_deliverable_edit",
    ),
    path(
        "email-marketing/<slug:slug>/work/<uuid:pk>/deliverables/<uuid:delivery_id>/review/",
        email_admin.request_review,
        name="email_marketing_request_review",
    ),
    path("analytics/", modules.analytics, name="module_analytics"),
    path("inbox/", leads_admin.inbox, name="module_inbox"),
    path("inbox/<int:pk>/", leads_admin.inbox_detail, name="inbox_detail"),
    path("inbox/<int:pk>/read/", leads_admin.inbox_read, name="inbox_read"),
    path("inbox/<int:pk>/archive/", leads_admin.inbox_archive, name="inbox_archive"),
    path("inbox/<int:pk>/spam/", leads_admin.inbox_spam, name="inbox_spam"),
    path("notifications/", leads_admin.notifications, name="module_notifications"),
    path("notifications/read/", leads_admin.notifications_read, name="notifications_read"),
    path("notifications/<int:pk>/", leads_admin.notification_open, name="notification_open"),
    # The service catalogue, built by apps.catalog.
    path("services/", catalog_admin.service_list, name="module_services"),
    path("services/new/", catalog_admin.service_create, name="catalog_create"),
    path("services/addons/", catalog_admin.addon_list, name="catalog_addons"),
    path("services/addons/new/", catalog_admin.addon_create, name="catalog_addon_create"),
    path(
        "services/addons/<int:pk>/delete/", catalog_admin.addon_delete, name="catalog_addon_delete"
    ),
    path("services/<int:pk>/", catalog_admin.service_edit, name="catalog_service"),
    path(
        "services/<int:pk>/visibility/",
        catalog_admin.service_visibility,
        name="catalog_service_visibility",
    ),
    path("services/<int:pk>/active/", catalog_admin.service_active, name="catalog_service_active"),
    path("services/<int:pk>/move/", catalog_admin.service_move, name="catalog_service_move"),
    path("services/<int:pk>/delete/", catalog_admin.service_delete, name="catalog_service_delete"),
    path(
        "services/<int:pk>/features/new/",
        catalog_admin.feature_create,
        name="catalog_feature_create",
    ),
    path(
        "services/features/<int:pk>/delete/",
        catalog_admin.feature_delete,
        name="catalog_feature_delete",
    ),
    path(
        "services/<int:pk>/packages/new/",
        catalog_admin.package_create,
        name="catalog_package_create",
    ),
    path("services/packages/<int:pk>/", catalog_admin.package_edit, name="catalog_package"),
    path(
        "services/packages/<int:pk>/delete/",
        catalog_admin.package_delete,
        name="catalog_package_delete",
    ),
    # Website content, built by the CMS domain but reached through the
    # staff dashboard like every other section.
    path("cms/", cms_admin.content_home, name="module_cms"),
    path("cms/wording/", copy_admin.editor, name="cms_wording"),
    path("cms/contact-details/", cms_admin.contact_settings, name="cms_contacts"),
    path("cms/pages/new/", cms_admin.page_create, name="cms_page_create"),
    path("cms/settings/", cms_admin.site_settings, name="cms_settings"),
    path("cms/pages/<int:pk>/", cms_admin.page_detail, name="cms_page"),
    path("cms/pages/<int:pk>/edit/", cms_admin.page_edit, name="cms_page_edit"),
    path("cms/pages/<int:pk>/publish/", cms_admin.page_publish, name="cms_page_publish"),
    path("cms/pages/<int:pk>/sections/new/", cms_admin.section_create, name="cms_section_create"),
    path("cms/sections/<int:pk>/", cms_admin.section_edit, name="cms_section"),
    path("cms/sections/<int:pk>/delete/", cms_admin.section_delete, name="cms_section_delete"),
    path("cms/sections/<int:pk>/move/", cms_admin.section_move, name="cms_section_move"),
    path("cms/sections/<int:pk>/visibility/", cms_admin.section_toggle, name="cms_section_toggle"),
    path("cms/sections/<int:pk>/items/new/", cms_admin.item_create, name="cms_item_create"),
    path("cms/items/<int:pk>/edit/", cms_admin.item_edit, name="cms_item_edit"),
    path("cms/items/<int:pk>/move/", cms_admin.item_move, name="cms_item_move"),
    path("cms/items/<int:pk>/toggle/", cms_admin.item_toggle, name="cms_item_toggle"),
    path("cms/items/<int:pk>/delete/", cms_admin.item_delete, name="cms_item_delete"),
    path("cms/<slug:key>/", cms_admin.collection_list, name="cms_collection"),
    path("cms/<slug:key>/new/", cms_admin.collection_edit, name="cms_collection_create"),
    path("cms/<slug:key>/<int:pk>/", cms_admin.collection_edit, name="cms_collection_edit"),
    path(
        "cms/<slug:key>/<int:pk>/delete/", cms_admin.collection_delete, name="cms_collection_delete"
    ),
    path("cms/<slug:key>/<int:pk>/move/", cms_admin.collection_move, name="cms_collection_move"),
    path(
        "cms/<slug:key>/<int:pk>/visibility/",
        cms_admin.collection_toggle,
        name="cms_collection_toggle",
    ),
    # The blog, built by the CMS domain.
    path("blog/", blog_admin.post_list, name="module_blog"),
    path("blog/new/", blog_admin.post_create, name="blog_create"),
    path("blog/<int:pk>/", blog_admin.post_edit, name="blog_edit"),
    path("blog/<int:pk>/publish/", blog_admin.post_publish, name="blog_publish"),
    path("blog/<int:pk>/delete/", blog_admin.post_delete, name="blog_delete"),
    path("media/", modules.media, name="module_media"),
    # Integration connections and sync history, built by apps.integrations.
    path("integrations/", integrations_admin.home, name="module_integrations"),
    path("integrations/history/", integrations_admin.sync_history, name="integration_history"),
    path(
        "integrations/<slug:provider>/",
        integrations_admin.provider_detail,
        name="integration_provider",
    ),
    path(
        "integrations/<slug:provider>/connections/new/",
        integrations_admin.connection_create,
        name="integration_connection_create",
    ),
    path(
        "integrations/<slug:provider>/credentials/",
        integrations_admin.credentials_update,
        name="integration_credentials_update",
    ),
    path(
        "integrations/<slug:provider>/sync/",
        integrations_admin.sync_now,
        name="integration_sync_now",
    ),
    path(
        "integrations/connections/<int:pk>/update/",
        integrations_admin.connection_update,
        name="integration_connection_update",
    ),
    path(
        "integrations/connections/<int:pk>/disconnect/",
        integrations_admin.connection_disconnect,
        name="integration_connection_disconnect",
    ),
    path("audit/", modules.audit, name="module_audit"),
    path("settings/", operating.settings_view, name="module_settings"),
]
