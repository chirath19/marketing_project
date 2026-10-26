"""Add the permissions the admin dashboard's navigation needs.

The nav lists Quote Requests, Notifications and Blog as sections of their
own, so each needs its own permission — mapping them onto a neighbouring
module would make those menu items impossible to grant or withhold
separately.
"""

from django.db import migrations


def sync(apps, schema_editor):
    from apps.permissions.management.commands.sync_permissions import sync_permissions

    sync_permissions()


def noop(apps, schema_editor):
    """Nothing to undo.

    Deleting the new permissions would silently strip them from any role
    that had been given them in the meantime, which is worse than leaving
    a few unused rows behind.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("permissions", "0002_sync_catalogue"),
    ]

    operations = [
        migrations.RunPython(sync, noop),
    ]
