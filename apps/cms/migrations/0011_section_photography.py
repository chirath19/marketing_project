"""Put the shipped photography on the pages that were drawing shapes.

Three of the seeded sections carried no picture and fell back to drawn
ornament: an abstract gold lens on the About hero, and a single asterisk
beside two long text blocks. The ornament is honest — it invents no data
— but it is also the thing that most makes a site read as unfinished,
because every competitor in this market shows the work.

So each of those three becomes the picture it was standing in for. The
two text blocks change type from "rich text" to "image and text", which
is the same fields plus a picture, so no content is lost; the About hero
simply gains an image and stops rendering the lens.

The home hero already had its photograph, attached as a 2MB PNG by
migration 0010. It is re-encoded here through the same optimiser as the
rest, which takes it to roughly a tenth of that.

Everything is guarded: a section an editor has already given a picture
of their own, or whose heading no longer matches the seed, is left
alone.
"""

from django.db import migrations
from django.utils import timezone

from apps.media.seed import attach_image, detach_image

#: page kind, section type the seed left, heading to match, source file,
#: stored name, alt text.
SECTIONS = [
    (
        "home", "rich_text", "Strategy before activity",
        "cp1.png", "home-strategy.jpg",
        "A quarterly campaign plan laid out on a desk: a channel strategy "
        "sheet, a timeline marked up with sticky notes, a budget allocation "
        "chart and a list of key initiatives.",
    ),
    (
        "home", "rich_text", "You see what we see",
        "sc3.png", "home-workspace.jpg",
        "Two colleagues at a screen reading a live campaign dashboard: total "
        "spend, leads, cost per conversion and return on ad spend above a "
        "table of individual campaigns.",
    ),
    (
        "about", "rich_text", "Make marketing spend defensible",
        "ab2.png", "about-reporting.jpg",
        "A printed marketing performance report being annotated by hand, "
        "showing sessions, conversion rate, cost per lead and revenue beside "
        "a traffic chart and a breakdown of leads by channel.",
    ),
]

HERO_IMAGE = (
    "about", "ab1.png", "about-team.jpg",
    "Four colleagues around a meeting table working through a marketing "
    "strategy funnel drawn on a whiteboard, with a website performance "
    "dashboard on the screen beside them.",
)

HOME_HERO = (
    "h1.png", "home-hero.jpg",
    "A marketer at a desk reviewing a marketing performance dashboard: "
    "sessions, conversion rate, cost per lead and return on ad spend, with "
    "leads broken down by channel.",
)


def _save(section) -> None:
    section.updated_at = timezone.now()
    section.save()


def add_photography(apps, schema_editor):
    PageSection = apps.get_model("cms", "PageSection")

    for kind, section_type, heading, source, name, alt in SECTIONS:
        section = PageSection.objects.filter(
            page__kind=kind, section_type=section_type, heading=heading,
        ).first()
        if section is None or section.image:
            continue
        if attach_image(section, source, name, alt):
            section.section_type = "image_text"
            _save(section)

    kind, source, name, alt = HERO_IMAGE
    hero = (PageSection.objects
            .filter(page__kind=kind, section_type="hero")
            .order_by("order").first())
    if hero is not None and not hero.image and attach_image(hero, source, name, alt):
        _save(hero)

    # The home hero: same picture, a tenth of the bytes.
    source, name, alt = HOME_HERO
    home_hero = (PageSection.objects
                 .filter(page__kind="home", section_type="hero")
                 .order_by("order").first())
    if (home_hero is not None
            and home_hero.image
            and home_hero.image.name.endswith(".png")
            and "home-hero" in home_hero.image.name):
        if attach_image(home_hero, source, name, alt, replace=True):
            _save(home_hero)


def remove_photography(apps, schema_editor):
    PageSection = apps.get_model("cms", "PageSection")

    for kind, section_type, heading, _source, name, _alt in SECTIONS:
        section = PageSection.objects.filter(
            page__kind=kind, section_type="image_text", heading=heading,
        ).first()
        if section is None:
            continue
        if detach_image(section, name.rsplit(".", 1)[0]):
            section.section_type = section_type
            _save(section)

    kind, _source, name, _alt = HERO_IMAGE
    hero = (PageSection.objects
            .filter(page__kind=kind, section_type="hero")
            .order_by("order").first())
    if hero is not None and detach_image(hero, name.rsplit(".", 1)[0]):
        _save(hero)

    # The home hero keeps its picture; only the encoding was this
    # migration's doing, and reversing to a larger file helps nobody.


class Migration(migrations.Migration):

    dependencies = [("cms", "0010_home_hero_image")]

    operations = [migrations.RunPython(add_photography, remove_photography)]
