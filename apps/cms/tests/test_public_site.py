"""The public website: what it renders, and what it refuses to."""

import pytest

from apps.cms.models import PublishStatus
from apps.cms.tests.factories import (
    make_faq,
    make_nav_item,
    make_page,
    make_section,
    make_social_link,
    make_team_member,
    make_testimonial,
    site_settings,
)

pytestmark = pytest.mark.django_db


# --- the seeded site --------------------------------------------------------


def test_the_home_page_renders(client):
    """Seeded by a migration, so a fresh install does not 404 at the door."""
    response = client.get("/")

    assert response.status_code == 200
    # Asserted against the seeded row rather than a literal, so
    # rewriting the headline is a content change and not a test failure.
    from apps.cms.models import Page, PageSection

    hero = PageSection.objects.filter(
        page=Page.objects.get(kind="home"), section_type="hero"
    ).first()
    assert hero is not None
    assert hero.heading.encode() in response.content


def test_the_about_and_contact_pages_render(client):
    assert client.get("/about/").status_code == 200
    assert client.get("/contact/").status_code == 200


def test_an_unknown_page_is_a_404(client):
    assert client.get("/no-such-page/").status_code == 404


# --- drafts -----------------------------------------------------------------


def test_a_draft_page_is_not_public(client):
    """The public views only ever read published rows — which is why they
    are exempt from the permission guard."""
    make_page("Secret", slug="secret", status=PublishStatus.DRAFT)

    assert client.get("/secret/").status_code == 404


def test_a_draft_page_is_hidden_from_staff_too(client):
    """The public site is the public site. Previewing a draft is a
    separate surface, not a logged-in visitor seeing more."""
    from apps.staff.tests.factories import PASSWORD, make_super_admin_user

    make_page("Secret", slug="secret", status=PublishStatus.DRAFT)
    admin = make_super_admin_user()
    client.login(username=admin.email, password=PASSWORD)

    assert client.get("/secret/").status_code == 404


def test_publishing_makes_a_page_appear(client):
    from apps.cms import services
    from apps.staff.tests.factories import make_super_admin_user

    page = make_page("New", slug="new", status=PublishStatus.DRAFT)
    assert client.get("/new/").status_code == 404

    services.publish_page(page=page, actor=make_super_admin_user())

    assert client.get("/new/").status_code == 200


# --- sections ---------------------------------------------------------------


def test_sections_render_in_order(client):
    page = make_page("Ordered", slug="ordered")
    make_section(page, "rich_text", body="SECOND BLOCK", order=20)
    make_section(page, "rich_text", body="FIRST BLOCK", order=10)

    body = client.get("/ordered/").content.decode()

    assert body.index("FIRST BLOCK") < body.index("SECOND BLOCK")


def test_a_hidden_section_does_not_render(client):
    page = make_page("Mixed", slug="mixed")
    make_section(page, "rich_text", body="VISIBLE BLOCK", order=10)
    make_section(page, "rich_text", body="HIDDEN BLOCK", order=20, is_visible=False)

    body = client.get("/mixed/").content

    assert b"VISIBLE BLOCK" in body
    assert b"HIDDEN BLOCK" not in body


@pytest.mark.parametrize("section_type", [
    "hero", "rich_text", "feature_grid", "stats", "testimonials", "team",
    "faq", "cta_band", "contact_details",
])
def test_every_section_type_renders(client, section_type):
    """A type with no template would 500 a live page."""
    page = make_page("All types", slug="all-types")
    make_section(page, section_type, heading="A heading", body="Words.",
                 cta_label="Go", cta_url="/go/")

    assert client.get("/all-types/").status_code == 200


def test_a_section_type_that_no_longer_exists_renders_nothing(client):
    """Removing a type from the code must not take a live page down."""
    page = make_page("Legacy", slug="legacy")
    section = make_section(page, "rich_text", body="Still here")
    # Bypass validation the way a stale database row would.
    type(section).objects.filter(pk=section.pk).update(section_type="retired_type")

    response = client.get("/legacy/")

    assert response.status_code == 200


def test_a_page_with_no_sections_still_renders(client):
    make_page("Empty", slug="empty")

    response = client.get("/empty/")

    assert response.status_code == 200
    assert b"nothing on this page yet" in response.content.lower()


# --- shared collections ------------------------------------------------------


def test_a_testimonials_section_shows_visible_testimonials_only(client):
    page = make_page("Quotes", slug="quotes")
    make_section(page, "testimonials", heading="Clients")
    make_testimonial(quote="SHOWN QUOTE", author_name="Visible Person")
    make_testimonial(quote="HIDDEN QUOTE", author_name="Hidden Person",
                     is_visible=False)

    body = client.get("/quotes/").content

    assert b"SHOWN QUOTE" in body
    assert b"HIDDEN QUOTE" not in body


def test_a_team_section_shows_visible_members_only(client):
    page = make_page("People", slug="people")
    make_section(page, "team", heading="Us")
    make_team_member(name="Shown Person")
    make_team_member(name="Hidden Person", is_visible=False)

    body = client.get("/people/").content

    assert b"Shown Person" in body
    assert b"Hidden Person" not in body


def test_an_faq_section_uses_details_so_it_works_without_javascript(client):
    page = make_page("Questions", slug="questions")
    make_section(page, "faq", heading="FAQ")
    make_faq(question="UNIQUE QUESTION", answer="An answer.")

    body = client.get("/questions/").content

    assert b"UNIQUE QUESTION" in body
    assert b"<details" in body


# --- chrome ------------------------------------------------------------------


def test_navigation_comes_from_the_database(client):
    make_nav_item(label="UNIQUE NAV LABEL", url="/somewhere/")

    assert b"UNIQUE NAV LABEL" in client.get("/").content


def test_a_hidden_navigation_item_does_not_render(client):
    make_nav_item(label="HIDDEN NAV", url="/x/", is_visible=False)

    assert b"HIDDEN NAV" not in client.get("/").content


def test_social_links_render_in_the_footer(client):
    make_social_link(platform="instagram", url="https://instagram.com/unique")

    assert b"https://instagram.com/unique" in client.get("/").content


def test_contact_details_come_from_site_settings(client):
    site_settings(contact_email="unique@agency.example",
                  contact_phone="+94 11 999 9999")

    body = client.get("/").content

    assert b"unique@agency.example" in body
    assert b"+94 11 999 9999" in body


def test_the_whatsapp_link_is_built_from_the_number(client):
    site_settings(whatsapp_number="+94 77 123 4567",
                  whatsapp_message="Hello")

    body = client.get("/").content.decode()

    assert "https://wa.me/94771234567" in body
    assert "text=Hello" in body


def test_no_whatsapp_number_means_no_whatsapp_link(client):
    site_settings(whatsapp_number="")

    assert b"wa.me" not in client.get("/").content


# --- banners -----------------------------------------------------------------


def test_a_live_banner_shows(client):
    from apps.cms.models import PromoBanner

    PromoBanner.objects.create(message="UNIQUE BANNER MESSAGE")

    assert b"UNIQUE BANNER MESSAGE" in client.get("/").content


def test_an_expired_banner_takes_itself_down(client):
    """So nobody has to remember to remove it."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.cms.models import PromoBanner

    PromoBanner.objects.create(
        message="OLD BANNER",
        starts_at=timezone.now() - timedelta(days=10),
        ends_at=timezone.now() - timedelta(days=1),
    )

    assert b"OLD BANNER" not in client.get("/").content


def test_a_future_banner_does_not_show_yet(client):
    from datetime import timedelta

    from django.utils import timezone

    from apps.cms.models import PromoBanner

    PromoBanner.objects.create(message="FUTURE BANNER",
                               starts_at=timezone.now() + timedelta(days=1))

    assert b"FUTURE BANNER" not in client.get("/").content


def test_a_home_only_banner_stays_off_other_pages(client):
    from apps.cms.models import PromoBanner

    make_page("Other", slug="other")
    PromoBanner.objects.create(message="HOME ONLY BANNER", placement="home_only")

    assert b"HOME ONLY BANNER" in client.get("/").content
    assert b"HOME ONLY BANNER" not in client.get("/other/").content


# --- SEO ---------------------------------------------------------------------


def test_a_page_uses_its_own_meta_title(client):
    make_page("Plain", slug="plain", meta_title="UNIQUE META TITLE")

    assert b"UNIQUE META TITLE" in client.get("/plain/").content


def test_a_page_without_a_meta_title_falls_back_to_its_title(client):
    make_page("Fallback Title", slug="fallback")

    assert b"Fallback Title" in client.get("/fallback/").content


def test_a_page_without_a_description_falls_back_to_the_site_default(client):
    site_settings(default_meta_description="SITE WIDE DESCRIPTION")
    make_page("Nodesc", slug="nodesc")

    assert b"SITE WIDE DESCRIPTION" in client.get("/nodesc/").content


def test_a_noindex_page_says_so(client):
    make_page("Thanks", slug="thanks", noindex=True)

    assert b'content="noindex, nofollow"' in client.get("/thanks/").content


def test_an_indexable_page_does_not(client):
    make_page("Normal", slug="normal")

    assert b"noindex" not in client.get("/normal/").content


def test_every_page_declares_a_canonical_url(client):
    assert b'rel="canonical"' in client.get("/").content


def test_open_graph_tags_are_present(client):
    body = client.get("/").content

    assert b'property="og:title"' in body
    assert b'property="og:description"' in body
    assert b'name="twitter:card"' in body


def test_structured_data_describes_the_organization(client):
    site_settings(site_name="Unique Agency Name")

    body = client.get("/").content

    assert b'"@type": "Organization"' in body
    assert b"Unique Agency Name" in body


def test_the_sitemap_lists_published_pages(client):
    make_page("Listed", slug="listed")

    body = client.get("/sitemap.xml").content

    assert b"/listed/" in body
    assert b"<urlset" in body


def test_the_sitemap_excludes_drafts_and_noindex_pages(client):
    make_page("Draft", slug="draft-page", status=PublishStatus.DRAFT)
    make_page("Hidden", slug="hidden-page", noindex=True)

    body = client.get("/sitemap.xml").content

    assert b"/draft-page/" not in body
    assert b"/hidden-page/" not in body


def test_robots_points_at_the_sitemap_and_excludes_private_areas(client):
    body = client.get("/robots.txt").content.decode()

    assert "Sitemap:" in body
    assert "/sitemap.xml" in body
    for path in ("/staff/", "/accounts/", "/api/", "/admin/"):
        assert f"Disallow: {path}" in body


# --- performance -------------------------------------------------------------


def test_a_page_costs_a_small_fixed_number_of_queries(client,
                                                      django_assert_max_num_queries):
    """Sections and their items are prefetched, so a long page costs no
    more than a short one.

    The budget includes one query for `tracking_settings`, the site-wide
    tag configuration every public page now reads to decide whether
    GTM/GA4/Pixel/RudderStack snippets render.
    """
    page = make_page("Long", slug="long")
    for index in range(8):
        section = make_section(page, "feature_grid", heading=f"Block {index}",
                               order=index * 10)
        for item in range(4):
            from apps.cms.tests.factories import make_item
            make_item(section, label=f"Item {item}", order=item)

    # Manual mode plus editable copy replace the former tracking lookup.
    with django_assert_max_num_queries(14):
        assert client.get("/long/").status_code == 200


# --- escaping ----------------------------------------------------------------


def test_cms_content_is_escaped(client):
    """Content is typed by staff, but a mistake must not become a script."""
    page = make_page("Escape", slug="escape")
    make_section(page, "rich_text", body="<script>alert(1)</script>")

    body = client.get("/escape/").content

    assert b"<script>alert(1)</script>" not in body
    assert b"&lt;script&gt;" in body


def test_every_seeded_section_satisfies_its_own_type_rules():
    """A migration bypasses `full_clean`, so a seeded section can violate
    the rules the CMS would enforce on an editor. It did: an image_text
    section shipped with no image and rendered an empty column."""
    from django.core.exceptions import ValidationError

    from apps.cms.models import PageSection

    problems = []
    for section in PageSection.objects.all():
        try:
            section.full_clean(exclude=["page"])
        except ValidationError as error:
            problems.append((str(section), error.message_dict))

    assert not problems, problems


def test_an_image_section_without_an_image_still_renders_one_column(client):
    page = make_page("Lopsided", slug="lopsided")
    section = make_section(page, "image_text", heading="No picture", body="Words.")
    type(section).objects.filter(pk=section.pk).update(image="")

    response = client.get("/lopsided/")

    assert response.status_code == 200
    assert b"lg:grid-cols-2" not in response.content.split(b"No picture")[0][-400:]
