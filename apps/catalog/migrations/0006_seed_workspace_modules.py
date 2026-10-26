"""Say which workspace area each service category unlocks.

A client's workspace is assembled from their active services: an active
service in the "Search" category opens the search area, and nothing else
does. Mapping that here rather than in code means a new category added
in the dashboard can declare what it unlocks without a deploy — and an
existing one can be pointed somewhere else without touching every row
that references it.
"""

from django.db import migrations

#: category slug -> workspace module key
MODULES = {
    "search": "seo",
    "paid": "paid_ads",
    "social": "social",
    "email": "email_marketing",
    "analytics": "analytics",
    "strategy": "strategy",
}


def seed(apps, schema_editor):
    ServiceCategory = apps.get_model("catalog", "ServiceCategory")

    for slug, module in MODULES.items():
        # Only where an editor has not already chosen one.
        ServiceCategory.objects.filter(slug=slug, workspace_module="").update(
            workspace_module=module
        )


def unseed(apps, schema_editor):
    ServiceCategory = apps.get_model("catalog", "ServiceCategory")
    ServiceCategory.objects.filter(slug__in=MODULES).update(workspace_module="")


class Migration(migrations.Migration):

    dependencies = [("catalog", "0005_category_workspace_module")]

    operations = [migrations.RunPython(seed, unseed)]
