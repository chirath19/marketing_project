"""Put the enquiry form on the contact page.

The page shipped with contact details only, because the form had nowhere
to store anything. It does now.
"""

from django.db import migrations
from django.utils import timezone


def add_form_section(apps, schema_editor):
    Page = apps.get_model("cms", "Page")
    PageSection = apps.get_model("cms", "PageSection")

    contact = Page.objects.filter(kind="contact").first()
    if contact is None:
        return
    if PageSection.objects.filter(page=contact, section_type="contact_form").exists():
        return

    now = timezone.now()
    PageSection.objects.create(
        page=contact, section_type="contact_form", order=15, tone="light",
        heading="Send us a message",
        subheading="We reply with a scoped plan, a price and a start date.",
        created_at=now, updated_at=now,
    )


def remove_form_section(apps, schema_editor):
    apps.get_model("cms", "PageSection").objects.filter(
        section_type="contact_form"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [("cms", "0003_category_tag_blogpost")]

    operations = [migrations.RunPython(add_form_section, remove_form_section)]
