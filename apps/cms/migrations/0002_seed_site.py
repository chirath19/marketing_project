"""Seed the site structure, with starter copy the agency then edits.

This is not sample data in the dashboard sense: it is the site's
structure, and every word of it is editable in the CMS. A fresh install
with no home page would 404 at the front door.

The copy is drawn from the supplied brief so the first thing anyone sees
is the intended message rather than lorem ipsum.
"""

from django.db import migrations
from django.utils import timezone


def seed(apps, schema_editor):
    SiteSettings = apps.get_model("cms", "SiteSettings")
    Page = apps.get_model("cms", "Page")
    PageSection = apps.get_model("cms", "PageSection")
    SectionItem = apps.get_model("cms", "SectionItem")
    NavigationItem = apps.get_model("cms", "NavigationItem")

    if Page.objects.exists():
        return

    now = timezone.now()

    SiteSettings.objects.get_or_create(defaults={
        "site_name": "Heliograph",
        "tagline": "Digital marketing agency",
        "contact_email": "hello@heliograph.agency",
        "default_meta_title": "Heliograph — digital marketing agency",
        "default_meta_description": (
            "Choose the services you need, build a quote in a minute, and "
            "track every result in your own dashboard."
        ),
    })

    home = Page.objects.create(
        title="Home", slug="home", kind="home", status="published",
        published_at=now,
        meta_title="Heliograph — marketing you can measure",
        meta_description=(
            "Search, paid ads, social and email, delivered against numbers "
            "you can see in your own dashboard."
        ),
        created_at=now, updated_at=now,
    )

    sections = [
        dict(section_type="hero", order=10, tone="navy",
             eyebrow="Digital marketing agency",
             heading="Marketing that you can measure, in a dashboard that is "
                     "actually yours.",
             subheading="Choose the services you need, build a quote in a "
                        "minute, and track every result in one place.",
             cta_label="Browse the catalogue", cta_url="/services/",
             secondary_cta_label="Talk to us", secondary_cta_url="/contact/"),
        dict(section_type="feature_grid", order=20, tone="light", columns=4,
             eyebrow="What we do",
             heading="Four services, one set of numbers",
             subheading="Each one reports into the same dashboard, so you can "
                        "see what is working against what it costs."),
        # rich_text, not image_text: no image ships with the seed, and
        # image_text requires one. A section that fails its own type's
        # rules renders as an empty column.
        dict(section_type="rich_text", order=30, tone="mist",
             eyebrow="How it works",
             heading="You see what we see",
             body="Every campaign we run reports into your dashboard: what is "
                  "live, what it has cost, and what it has returned.\n\n"
                  "No monthly slide deck, no waiting for a report. When "
                  "something needs your approval, it appears there too."),
        dict(section_type="testimonials", order=40, tone="light",
             eyebrow="Clients", heading="What it is like to work with us"),
        dict(section_type="faq", order=50, tone="mist",
             heading="Questions we are asked"),
        dict(section_type="cta_band", order=60, tone="navy",
             heading="Tell us what you want to achieve",
             subheading="We reply with a scoped plan, a price and a start date.",
             cta_label="Get a quote", cta_url="/contact/"),
    ]

    for spec in sections:
        PageSection.objects.create(page=home, created_at=now, updated_at=now, **spec)

    features = PageSection.objects.get(page=home, section_type="feature_grid")
    for order, (label, body) in enumerate([
        ("Search", "Technical fixes, content and links, measured against the "
                   "positions that bring customers."),
        ("Paid ads", "Google, Meta and LinkedIn, managed against cost per "
                     "customer rather than clicks."),
        ("Social media", "A steady rhythm of posts and replies, with creative "
                         "tested every month."),
        ("Email", "Welcome, win-back and newsletter flows, built and measured "
                  "for you."),
    ], start=1):
        SectionItem.objects.create(section=features, label=label, body=body,
                                   order=order * 10, created_at=now, updated_at=now)

    about = Page.objects.create(
        title="About", slug="about", kind="about", status="published",
        published_at=now,
        meta_description="Who we are and how we work.",
        created_at=now, updated_at=now,
    )
    PageSection.objects.create(
        page=about, section_type="hero", order=10, tone="mist",
        eyebrow="About us", heading="A small team, accountable to numbers",
        subheading="We would rather show you a dashboard than a slide deck.",
        created_at=now, updated_at=now,
    )
    PageSection.objects.create(
        page=about, section_type="rich_text", order=20, tone="light",
        heading="How we work",
        body="We scope the work, agree a price and a start date, and then run "
             "it against the numbers we agreed.\n\n"
             "Everything we do appears in your dashboard as it happens: what "
             "is live, what it costs, and what it returns.",
        created_at=now, updated_at=now,
    )
    PageSection.objects.create(
        page=about, section_type="team", order=30, tone="mist",
        heading="The people on your account",
        created_at=now, updated_at=now,
    )

    contact = Page.objects.create(
        title="Contact", slug="contact", kind="contact", status="published",
        published_at=now,
        meta_description="Email, phone and WhatsApp.",
        created_at=now, updated_at=now,
    )
    PageSection.objects.create(
        page=contact, section_type="hero", order=10, tone="mist",
        eyebrow="Contact", heading="Tell us what you want to achieve",
        subheading="We reply with a scoped plan, a price and a start date.",
        created_at=now, updated_at=now,
    )
    PageSection.objects.create(
        page=contact, section_type="contact_details", order=20, tone="light",
        heading="How to reach us",
        created_at=now, updated_at=now,
    )

    nav = [
        ("Services", "header", 10, None, "/services/", False),
        ("About", "header", 20, about, "", False),
        ("Contact", "header", 30, contact, "", False),
        ("Get a quote", "header", 40, contact, "", True),
        ("About", "footer_primary", 10, about, "", False),
        ("Contact", "footer_primary", 20, contact, "", False),
        ("Privacy policy", "legal", 10, None, "/privacy/", False),
    ]
    for label, placement, order, page, url, is_cta in nav:
        NavigationItem.objects.create(
            label=label, placement=placement, order=order,
            page=page, url=url, is_cta=is_cta,
            created_at=now, updated_at=now,
        )


def unseed(apps, schema_editor):
    for model in ("NavigationItem", "SectionItem", "PageSection", "Page"):
        apps.get_model("cms", model).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [("cms", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
