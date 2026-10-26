"""Create the one `TrackingSettings` row up front.

Every public page's `tracking_settings` context processor reads this
singleton on first access. Without a seeded row, the first request
after a fresh deploy pays for a `get_or_create` insert instead of a
plain lookup — this migration is what keeps that cost at exactly one
query per request, the same way `cms.0002_seed_site` already does for
`SiteSettings`.
"""

from django.db import migrations


def seed(apps, schema_editor):
    TrackingSettings = apps.get_model("tracking", "TrackingSettings")
    TrackingSettings.objects.get_or_create(pk=1)


def unseed(apps, schema_editor):
    apps.get_model("tracking", "TrackingSettings").objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [("tracking", "0001_tracking_core")]

    operations = [migrations.RunPython(seed, unseed)]
