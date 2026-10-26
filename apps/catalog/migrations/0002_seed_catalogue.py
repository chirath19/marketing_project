"""Seed the catalogue from the supplied reference.

Structure plus starter content, like the CMS pages: every price, name and
feature below is editable in the staff dashboard. A fresh install with an
empty catalogue would show a services page with nothing on it.

The twelve services and their prices come from the brief's own catalogue
page, so the first thing anyone sees is the intended offering rather than
placeholder text.
"""

from decimal import Decimal

from django.db import migrations
from django.utils import timezone


CATEGORIES = [
    ("Search", "search", 10, "Technical fixes, content and links.", "🔍"),
    ("Paid", "paid", 20, "Google, Meta and LinkedIn, managed against cost per customer.", "◎"),
    ("Social", "social", 30, "A steady rhythm of posts, replies and creators.", "◆"),
    ("Email", "email", 40, "Flows and newsletters, built and measured.", "✉"),
    ("Analytics", "analytics", 50, "Tracking, dashboards and the numbers behind them.", "▲"),
]

#: name, slug, category, short description, price, billing, featured, features
SERVICES = [
    ("Technical SEO audit", "technical-seo-audit", "search",
     "A full review of speed, structure and indexing, with a fix list ranked "
     "by impact.", Decimal("1500"), "one_time", False,
     ["Crawl and index review", "Core Web Vitals assessment",
      "Site structure and internal linking", "Prioritised fix list"]),

    ("SEO growth retainer", "seo-growth-retainer", "search",
     "Monthly content, on-page work and link building to climb the results "
     "page.", Decimal("2400"), "monthly", True,
     ["Monthly content plan", "On-page optimisation", "Link building outreach",
      "Monthly reporting"]),

    ("Local search", "local-search", "search",
     "Google Business Profile, local pages and reviews for shops and service "
     "areas.", Decimal("900"), "monthly", False,
     ["Google Business Profile management", "Local landing pages",
      "Review generation", "Local citation clean-up"]),

    ("Google Ads management", "google-ads-management", "paid",
     "Search and Shopping campaigns managed against cost per customer.",
     Decimal("1800"), "monthly", True,
     ["Campaign build and structure", "Weekly optimisation",
      "Creative and copy testing", "Conversion tracking"]),

    ("Meta Ads management", "meta-ads-management", "paid",
     "Facebook and Instagram campaigns with fresh creative tested every month.",
     Decimal("1800"), "monthly", False,
     ["Campaign build and structure", "Monthly creative refresh",
      "Audience testing", "Conversion tracking"]),

    ("LinkedIn lead generation", "linkedin-lead-generation", "paid",
     "Lead-form campaigns that reach decision-makers by job title and company.",
     Decimal("2200"), "monthly", False,
     ["Audience build by role and company", "Lead form setup",
      "Creative and copy testing", "CRM handover"]),

    ("Social media management", "social-media-management", "social",
     "A steady posting rhythm with community replies across two channels.",
     Decimal("1600"), "monthly", False,
     ["Content calendar", "Post design and copy", "Community replies",
      "Monthly reporting"]),

    ("Creator partnerships", "creator-partnerships", "social",
     "We find, brief and manage creators who fit your brand and audience.",
     Decimal("2000"), "monthly", False,
     ["Creator sourcing and vetting", "Briefing and contracts",
      "Content approval", "Performance reporting"]),

    ("Email automation setup", "email-automation-setup", "email",
     "Welcome, abandoned cart and win-back flows built and tested.",
     Decimal("2200"), "one_time", False,
     ["Flow mapping", "Copy and design", "Build and testing",
      "Handover and documentation"]),

    ("Monthly newsletter", "monthly-newsletter", "email",
     "Strategy, copy, design and sending for your regular customer email.",
     Decimal("800"), "monthly", False,
     ["Monthly strategy", "Copy and design", "Send and schedule",
      "Performance reporting"]),

    ("Tracking setup: GTM and Meta Pixel", "tracking-setup", "analytics",
     "Tag Manager container, Meta Pixel, conversion events and consent "
     "banner, tested end to end.", Decimal("1200"), "one_time", False,
     ["Tag Manager container", "Meta Pixel and conversion events",
      "Consent banner", "End-to-end testing"]),

    ("Reporting dashboard", "reporting-dashboard", "analytics",
     "A live client dashboard that joins search, ads, social and email "
     "results.", Decimal("600"), "monthly", True,
     ["Data sources connected", "Dashboard build", "Monthly goals",
      "Ongoing maintenance"]),
]

#: The SEO retainer ships with tiers, so the comparison table has
#: something real to show. service slug, then (name, summary, price,
#: recommended, which features are included by index).
PACKAGES = [
    ("seo-growth-retainer", [
        ("Starter", "One market, steady progress.", Decimal("2400"), False, [0, 1, 3]),
        ("Growth", "The usual choice for a growing site.", Decimal("3800"), True,
         [0, 1, 2, 3]),
        ("Scale", "Several markets or a large catalogue.", Decimal("6500"), False,
         [0, 1, 2, 3]),
    ]),
]

ADDONS = [
    ("Landing page build", "landing-page-build", None,
     "A single conversion-focused page, designed and built.",
     Decimal("1400"), "one_time"),
    ("Monthly strategy call", "monthly-strategy-call", None,
     "An hour with your account manager and a specialist.",
     Decimal("300"), "monthly"),
]


def seed(apps, schema_editor):
    ServiceCategory = apps.get_model("catalog", "ServiceCategory")
    Service = apps.get_model("catalog", "Service")
    ServiceFeature = apps.get_model("catalog", "ServiceFeature")
    ServicePackage = apps.get_model("catalog", "ServicePackage")
    PackageFeature = apps.get_model("catalog", "PackageFeature")
    ServiceAddon = apps.get_model("catalog", "ServiceAddon")

    if Service.objects.exists():
        return

    now = timezone.now()
    categories = {}

    for name, slug, order, description, icon in CATEGORIES:
        categories[slug] = ServiceCategory.objects.create(
            name=name, slug=slug, order=order, short_description=description,
            icon=icon, created_at=now, updated_at=now,
        )

    services = {}
    for index, (name, slug, category, description, price, billing,
                featured, features) in enumerate(SERVICES, start=1):
        service = Service.objects.create(
            name=name, slug=slug, category=categories[category],
            short_description=description, price=price, currency="USD",
            billing_type=billing, is_featured=featured, order=index * 10,
            created_at=now, updated_at=now,
        )
        services[slug] = service

        for feature_index, label in enumerate(features, start=1):
            ServiceFeature.objects.create(
                service=service, label=label, order=feature_index * 10,
                created_at=now, updated_at=now,
            )

    for service_slug, tiers in PACKAGES:
        service = services[service_slug]
        feature_rows = list(
            ServiceFeature.objects.filter(service=service).order_by("order", "pk")
        )

        for tier_index, (tier_name, summary, price, recommended,
                         included) in enumerate(tiers, start=1):
            package = ServicePackage.objects.create(
                service=service, name=tier_name,
                slug=tier_name.lower().replace(" ", "-"),
                summary=summary, price=price, currency="USD",
                billing_type="monthly", is_recommended=recommended,
                order=tier_index * 10, created_at=now, updated_at=now,
            )
            for position in included:
                if position < len(feature_rows):
                    PackageFeature.objects.create(
                        package=package, feature=feature_rows[position],
                        is_included=True,
                    )

    for index, (name, slug, service_slug, description, price,
                billing) in enumerate(ADDONS, start=1):
        ServiceAddon.objects.create(
            name=name, slug=slug,
            service=services[service_slug] if service_slug else None,
            short_description=description, price=price, currency="USD",
            billing_type=billing, order=index * 10,
            created_at=now, updated_at=now,
        )


def unseed(apps, schema_editor):
    for model in ("PackageFeature", "ServicePackage", "ServiceFeature",
                  "ServiceAddon", "Service", "ServiceCategory"):
        apps.get_model("catalog", model).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [("catalog", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
