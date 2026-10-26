"""Create the catalogue's Permission rows, and the default roles.

Runs as a migration so a fresh database — a new developer's, or a Railway
deploy — comes up with the permission vocabulary already present. The
`sync_permissions` command does the same thing and is what a later
catalogue change should be applied with.

The default roles exist so the platform is usable on day one. They are
marked `is_system`, which stops them being deleted but not edited: an
agency's idea of what an SEO specialist may do is theirs to change.
"""

from django.db import migrations

DEFAULT_ROLES = {
    "Account Manager": {
        "description": "Owns the client relationship. Sees everything for "
                       "their accounts and approves work going out.",
        "permissions": [
            "organizations_view", "organizations_edit", "organizations_export",
            "campaigns_view", "campaigns_create", "campaigns_edit",
            "campaigns_approve", "campaigns_export",
            "approvals_view", "approvals_create", "approvals_approve",
            "messaging_view", "messaging_create", "messaging_edit",
            "leads_view", "leads_edit", "leads_assign", "leads_export",
            "subscriptions_view", "subscriptions_edit", "subscriptions_approve",
            "analytics_view", "analytics_export",
            "seo_view", "paid_ads_view", "social_view", "email_marketing_view",
            "media_view",
        ],
    },
    "SEO Specialist": {
        "description": "Delivers SEO work for assigned clients only.",
        "permissions": [
            "organizations_view",
            "campaigns_view", "campaigns_edit",
            "seo_view", "seo_create", "seo_edit", "seo_delete", "seo_export",
            "analytics_view", "analytics_export",
            "media_view", "media_create",
            "messaging_view", "messaging_create",
        ],
    },
    "Paid Ads Specialist": {
        "description": "Delivers paid media for assigned clients only.",
        "permissions": [
            "organizations_view",
            "campaigns_view", "campaigns_edit",
            "paid_ads_view", "paid_ads_create", "paid_ads_edit",
            "paid_ads_delete", "paid_ads_export",
            "analytics_view", "analytics_export",
            "media_view", "media_create",
            "messaging_view", "messaging_create",
        ],
    },
    "Social Media Manager": {
        "description": "Plans and publishes social content for assigned clients.",
        "permissions": [
            "organizations_view",
            "campaigns_view", "campaigns_edit",
            "social_view", "social_create", "social_edit", "social_delete",
            "social_publish", "social_export",
            "media_view", "media_create", "media_edit",
            "messaging_view", "messaging_create",
        ],
    },
    "Analyst": {
        "description": "Reads and reports. Changes nothing.",
        "permissions": [
            "organizations_view", "organizations_export",
            "campaigns_view", "campaigns_export",
            "seo_view", "seo_export", "paid_ads_view", "paid_ads_export",
            "social_view", "social_export",
            "email_marketing_view", "email_marketing_export",
            "analytics_view", "analytics_create", "analytics_edit",
            "analytics_export",
        ],
    },
    "Content Editor": {
        "description": "Writes and publishes the public website and catalogue.",
        "permissions": [
            "cms_view", "cms_create", "cms_edit", "cms_delete", "cms_publish",
            "catalog_view", "catalog_create", "catalog_edit", "catalog_publish",
            "media_view", "media_create", "media_edit",
        ],
    },
    "Operations Manager": {
        "description": "Runs the agency side: staff, assignments and settings.",
        "permissions": [
            "staff_view", "staff_create", "staff_edit", "staff_assign",
            "staff_manage",
            "roles_view",
            "organizations_view", "organizations_create", "organizations_edit",
            "organizations_assign", "organizations_manage", "organizations_export",
            "settings_view", "settings_edit",
            "integrations_view", "integrations_edit",
            "audit_view", "audit_export",
            "subscriptions_view", "subscriptions_edit", "subscriptions_approve",
        ],
    },
}


def create_catalogue(apps, schema_editor):
    from apps.permissions.management.commands.sync_permissions import sync_permissions

    sync_permissions()

    Permission = apps.get_model("auth", "Permission")
    Role = apps.get_model("permissions", "Role")
    RolePermission = apps.get_model("permissions", "RolePermission")

    from django.utils.text import slugify

    by_codename = {
        permission.codename: permission
        for permission in Permission.objects.filter(
            content_type__app_label="permissions",
            content_type__model="platformpermission",
        )
    }

    for name, spec in DEFAULT_ROLES.items():
        role, _created = Role.objects.get_or_create(
            name=name,
            defaults={
                "slug": slugify(name)[:140],
                "description": spec["description"],
                "is_system": True,
            },
        )

        for codename in spec["permissions"]:
            permission = by_codename.get(codename)
            if permission is None:
                # A role referencing a permission the catalogue no longer
                # declares is a bug, but failing a migration over it would
                # block a deploy for something recoverable.
                continue
            RolePermission.objects.get_or_create(role=role, permission=permission)


def remove_catalogue(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Role = apps.get_model("permissions", "Role")

    Role.objects.filter(is_system=True, name__in=DEFAULT_ROLES).delete()
    Permission.objects.filter(content_type__app_label="permissions",
                              content_type__model="platformpermission").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("permissions", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(create_catalogue, remove_catalogue),
    ]
