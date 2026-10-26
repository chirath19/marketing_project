"""Give the services that have a picture, their picture.

Twenty-eight catalogue cards drawn from the same three line motifs is a
wall, and a service page whose only illustration is a gradient asks the
buyer to take the description on faith. Five of the shipped photographs
show the actual working surface of a service — a crawl report, a tag
container, a publishing board, a content calendar, a campaign dashboard
— so each goes on the service it depicts.

Only those five. A photograph that does not show the thing it sits next
to is decoration, and a catalogue where some cards carry a real picture
and the rest carry none reads as deliberate; one where every card
carries a vaguely office-themed stock photo does not.

Guarded the same way as the CMS seed: a service an editor has already
given an image of their own keeps it.
"""

from django.db import migrations
from django.utils import timezone

from apps.media.seed import attach_image, detach_image

#: service slug, source file, stored name, alt text.
IMAGES = [
    (
        "technical-seo-audit", "sc1.png", "service-seo-audit.jpg",
        "An SEO audit dashboard showing organic clicks, impressions, average "
        "click-through rate and position, a list of technical issues found, "
        "and a crawl table of URLs with their status codes.",
    ),
    (
        "google-ads-management", "sc3.png", "service-google-ads.jpg",
        "A paid advertising dashboard showing total spend, leads, cost per "
        "conversion and return on ad spend, above a table of campaigns with "
        "their budget, impressions, clicks and conversions.",
    ),
    (
        "social-media-management", "sc2.png", "service-social-media.jpg",
        "A social media content board with columns for ideas, in progress, "
        "scheduled and published posts, beside a phone editing a short video "
        "for one of them.",
    ),
    (
        "creator-partnerships", "sc4.png", "service-creator-content.jpg",
        "A content calendar of scheduled posts for the month beside a phone "
        "trimming a product video, with a list of content ideas and platforms "
        "written out in a notebook.",
    ),
    (
        "tracking-setup", "sc5.png", "service-tracking.jpg",
        "A tag manager workspace listing analytics and conversion tags with "
        "their triggers and status, an event flow from page view through to "
        "purchase, and a live debugging view of events as they fire.",
    ),
]


def add_photography(apps, schema_editor):
    Service = apps.get_model("catalog", "Service")

    for slug, source, name, alt in IMAGES:
        service = Service.objects.filter(slug=slug).first()
        if service is None or service.image:
            continue
        if attach_image(service, source, name, alt):
            service.updated_at = timezone.now()
            service.save()


def remove_photography(apps, schema_editor):
    Service = apps.get_model("catalog", "Service")

    for slug, _source, name, _alt in IMAGES:
        service = Service.objects.filter(slug=slug).first()
        if service is not None and detach_image(service, name.rsplit(".", 1)[0]):
            service.updated_at = timezone.now()
            service.save()


class Migration(migrations.Migration):

    dependencies = [("catalog", "0007_module_choices")]

    operations = [migrations.RunPython(add_photography, remove_photography)]
