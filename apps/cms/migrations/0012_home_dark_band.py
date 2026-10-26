"""Give the home page a second dark beat.

The page runs hero, then six cream sections, then the closing band. The
hero is now a dark stage, which means the whole middle of the page reads
as one long pale stretch with the dark bookends a screen and a half
apart.

"You see what we see" is the section to turn over: it is the one block
on the home page that is about the client's own workspace rather than
about the service, and a dark surface is what that product is. Changing
its tone is all that is needed — `image_text.html` renders a navy
section as the glass treatment, with the drifting light field behind it,
exactly as the hero does.

Guarded on the current value, so an editor who has already chosen a tone
for this section keeps it.
"""

from django.db import migrations
from django.utils import timezone

HEADING = "You see what we see"


def darken(apps, schema_editor):
    PageSection = apps.get_model("cms", "PageSection")
    PageSection.objects.filter(
        page__kind="home", heading=HEADING, tone="light",
    ).update(tone="navy", updated_at=timezone.now())


def lighten(apps, schema_editor):
    PageSection = apps.get_model("cms", "PageSection")
    PageSection.objects.filter(
        page__kind="home", heading=HEADING, tone="navy",
    ).update(tone="light", updated_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [("cms", "0011_section_photography")]

    operations = [migrations.RunPython(darken, lighten)]
