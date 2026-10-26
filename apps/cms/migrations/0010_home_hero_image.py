"""Give the home page hero the photograph that ships with the repo.

The hero renders `section.image` when there is one and falls back to the
drawn sculpture when there is not, so this migration only has to put the
file on the section. The source lives in `assets/images/` — unserved
build input, like the Tailwind sources beside it — and is copied into
whichever media backend is configured, local disk or Cloudinary.

Only the seeded section is touched, and only while it still has no image
of its own: once an editor has chosen a picture in the CMS, that choice
outranks anything shipped here.
"""

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import migrations
from django.utils import timezone

SOURCE = Path("assets") / "images" / "h1.png"
TARGET_NAME = "home-hero.png"
ALT = (
    "A marketer at a desk reviewing a marketing performance dashboard: "
    "sessions, conversion rate, cost per lead and return on ad spend, with "
    "leads broken down by channel."
)


def attach_hero_image(apps, schema_editor):
    PageSection = apps.get_model("cms", "PageSection")

    source = Path(settings.BASE_DIR) / SOURCE
    if not source.is_file():
        # A deployment that ships without the asset keeps the drawn
        # fallback rather than failing the migration.
        return

    hero = (PageSection.objects
            .filter(page__kind="home", section_type="hero")
            .order_by("order")
            .first())
    if hero is None or hero.image:
        return

    with source.open("rb") as fh:
        hero.image.save(TARGET_NAME, File(fh), save=False)
    hero.image_alt = ALT
    hero.updated_at = timezone.now()
    hero.save(update_fields=["image", "image_alt", "updated_at"])


def detach_hero_image(apps, schema_editor):
    PageSection = apps.get_model("cms", "PageSection")

    hero = (PageSection.objects
            .filter(page__kind="home", section_type="hero")
            .order_by("order")
            .first())
    if hero is None or not hero.image:
        return
    if Path(hero.image.name).name.startswith(Path(TARGET_NAME).stem):
        hero.image.delete(save=False)
        hero.image = ""
        hero.image_alt = ""
        hero.updated_at = timezone.now()
        hero.save(update_fields=["image", "image_alt", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [("cms", "0009_section_body_help")]

    operations = [migrations.RunPython(attach_hero_image, detach_hero_image)]
