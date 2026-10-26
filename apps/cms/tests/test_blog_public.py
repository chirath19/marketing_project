"""The public blog."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.cms.tests.factories import make_category, make_post, make_tag

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _blog_starts_empty():
    """Clear the seeded articles before each test in this module.

    A migration seeds four articles so a fresh install does not launch
    with an empty blog. These tests state their own fixtures and assert
    on ordering, filtering and counts — the seeded rows would quietly
    join every one of those assertions.
    """
    from apps.cms.models import BlogPost, Category, Tag

    BlogPost.objects.all().delete()
    Category.objects.all().delete()
    Tag.objects.all().delete()


# --- listing -----------------------------------------------------------------


def test_the_listing_renders(client):
    make_post("Hello world")

    response = client.get("/blog/")

    assert response.status_code == 200
    assert b"Hello world" in response.content


def test_an_empty_blog_says_so(client):
    response = client.get("/blog/")

    assert response.status_code == 200
    # An intentional empty state: it says why the page is bare and
    # offers somewhere useful to go, rather than rendering a blank list.
    assert b"No articles yet" in response.content
    assert b"Browse services" in response.content


def test_posts_are_newest_first(client):
    older = make_post("Older post", published_at=timezone.now() - timedelta(days=5))
    newer = make_post("Newer post", published_at=timezone.now())

    body = client.get("/blog/").content.decode()

    assert body.index(newer.title) < body.index(older.title)


def test_a_draft_does_not_appear(client):
    make_post("Secret draft", published=False)

    assert b"Secret draft" not in client.get("/blog/").content


def test_a_draft_detail_page_is_a_404(client):
    make_post("Secret draft", published=False)

    assert client.get("/blog/secret-draft/").status_code == 404


def test_a_draft_is_hidden_from_staff_too(client):
    """The public blog is the public blog. Previewing is a separate
    surface, not a signed-in visitor seeing more."""
    from apps.staff.tests.factories import PASSWORD, make_super_admin_user

    make_post("Secret draft", published=False)
    admin = make_super_admin_user()
    client.login(username=admin.email, password=PASSWORD)

    assert client.get("/blog/secret-draft/").status_code == 404


def test_a_future_dated_post_is_held_back(client):
    """So a post can be written on Monday and appear on Thursday without
    anyone having to remember."""
    make_post("Scheduled post",
              published_at=timezone.now() + timedelta(days=3))

    assert b"Scheduled post" not in client.get("/blog/").content
    assert client.get("/blog/scheduled-post/").status_code == 404


def test_a_post_dated_in_the_past_appears(client):
    make_post("Back dated", published_at=timezone.now() - timedelta(days=1))

    assert b"Back dated" in client.get("/blog/").content


# --- pagination --------------------------------------------------------------


def test_the_listing_paginates(client):
    for index in range(14):
        make_post(f"Post number {index}",
                  published_at=timezone.now() - timedelta(hours=index))

    first = client.get("/blog/")
    second = client.get("/blog/", {"page": 2})

    assert first.context["posts"].count() == 12
    assert second.context["posts"].count() == 2


def test_a_page_number_past_the_end_shows_the_first_page(client):
    """Better than a 404 for someone following a stale link."""
    make_post("Only post")

    response = client.get("/blog/", {"page": 99})

    assert response.status_code == 200
    assert b"Only post" in response.content


def test_a_nonsense_page_number_does_not_error(client):
    make_post("Only post")

    assert client.get("/blog/", {"page": "banana"}).status_code == 200


def test_page_two_is_canonical_to_itself(client):
    """Pointing every page at page one tells a crawler they are the same
    page, and the rest never get indexed."""
    for index in range(14):
        make_post(f"Post {index}", published_at=timezone.now() - timedelta(hours=index))

    body = client.get("/blog/", {"page": 2}).content

    assert b'rel="canonical"' in body
    assert b"/blog/?page=2" in body
    assert b'rel="prev"' in body


# --- categories and tags -----------------------------------------------------


def test_a_category_page_shows_only_its_posts(client):
    strategy = make_category("Strategy")
    make_post("In strategy", category=strategy)
    make_post("Somewhere else")

    body = client.get("/blog/category/strategy/").content

    assert b"In strategy" in body
    assert b"Somewhere else" not in body


def test_a_tag_page_shows_only_tagged_posts(client):
    seo = make_tag("SEO")
    make_post("Tagged post", tags=[seo])
    make_post("Untagged post")

    body = client.get("/blog/tag/seo/").content

    assert b"Tagged post" in body
    assert b"Untagged post" not in body


def test_an_empty_category_is_not_offered_in_the_filter(client):
    """A category page with nothing on it is a dead end for a visitor and
    a thin page for a crawler."""
    make_category("Empty category")
    used = make_category("Used category")
    make_post("A post", category=used)

    body = client.get("/blog/").content

    assert b"Used category" in body
    assert b"Empty category" not in body


def test_a_category_with_only_a_draft_counts_as_empty(client):
    category = make_category("Drafts only")
    make_post("Hidden", category=category, published=False)

    assert b"Drafts only" not in client.get("/blog/").content


def test_an_unknown_category_is_a_404(client):
    assert client.get("/blog/category/nope/").status_code == 404


def test_a_hidden_category_is_a_404(client):
    make_category("Retired", is_visible=False)

    assert client.get("/blog/category/retired/").status_code == 404


def test_the_active_category_is_marked_current(client):
    category = make_category("Strategy")
    make_post("A post", category=category)

    body = client.get("/blog/category/strategy/").content

    assert b'aria-current="page"' in body


# --- detail ------------------------------------------------------------------


def test_the_detail_page_renders_the_body(client):
    make_post("Readable", content="## A heading\n\nAnd a paragraph.")

    body = client.get("/blog/readable/").content

    assert b"<h2" in body
    assert b"And a paragraph." in body


def test_the_detail_page_shows_the_byline_and_reading_time(client):
    from apps.accounts.tests.factories import make_user

    author = make_user(email="writer@heliograph.agency", full_name="Sam Writer")
    make_post("Bylined", author=author)

    body = client.get("/blog/bylined/").content

    assert b"Sam Writer" in body
    assert b"min read" in body


def test_an_unknown_post_is_a_404(client):
    assert client.get("/blog/no-such-post/").status_code == 404


def test_post_content_cannot_inject_markup(client):
    """Authors are staff, but a paste from elsewhere must not become a
    script tag."""
    make_post("Risky", content="<script>alert(1)</script>")

    body = client.get("/blog/risky/").content

    assert b"<script>alert(1)</script>" not in body
    assert b"&lt;script&gt;" in body


# --- related posts -----------------------------------------------------------


def test_related_posts_come_from_the_same_category(client):
    strategy = make_category("Strategy")
    make_post("The post being read", category=strategy)
    make_post("A sibling", category=strategy)
    make_post("Unrelated")

    body = client.get("/blog/the-post-being-read/").content

    assert b"A sibling" in body
    assert b"Unrelated" not in body


def test_related_posts_fall_back_to_shared_tags(client):
    seo = make_tag("SEO")
    make_post("The post being read", tags=[seo])
    make_post("Shares a tag", tags=[seo])

    assert b"Shares a tag" in client.get("/blog/the-post-being-read/").content


def test_a_post_is_never_related_to_itself(client):
    """The only post in its category has nothing to read next, so the
    section is absent rather than showing the post again."""
    strategy = make_category("Strategy")
    make_post("Lonely", category=strategy)

    response = client.get("/blog/lonely/")

    assert response.context["related"] == []
    assert b"Read next" not in response.content


def test_a_draft_is_never_shown_as_related(client):
    strategy = make_category("Strategy")
    make_post("The post being read", category=strategy)
    make_post("A draft sibling", category=strategy, published=False)

    assert b"A draft sibling" not in client.get("/blog/the-post-being-read/").content


# --- SEO ---------------------------------------------------------------------


def test_a_post_uses_its_own_meta_title(client):
    make_post("Plain title", meta_title="UNIQUE SEO TITLE")

    assert b"UNIQUE SEO TITLE" in client.get("/blog/plain-title/").content


def test_a_post_without_a_meta_description_falls_back_to_its_excerpt(client):
    make_post("Described", excerpt="A SHORT SUMMARY OF THE POST")

    assert b"A SHORT SUMMARY OF THE POST" in client.get("/blog/described/").content


def test_an_excerptless_post_summarises_its_opening(client):
    make_post("Autosummary", excerpt="",
              content="The opening sentence carries the summary.")

    assert b"The opening sentence" in client.get("/blog/autosummary/").content


def test_a_post_carries_article_structured_data(client):
    make_post("Structured")

    body = client.get("/blog/structured/").content

    assert b'"@type": "BlogPosting"' in body
    assert b'"datePublished"' in body


def test_posts_appear_in_the_sitemap(client):
    make_post("In the sitemap")

    body = client.get("/sitemap.xml").content

    assert b"/blog/in-the-sitemap/" in body


def test_drafts_stay_out_of_the_sitemap(client):
    make_post("Not in the sitemap", published=False)

    assert b"/blog/not-in-the-sitemap/" not in client.get("/sitemap.xml").content


def test_the_feed_lists_recent_posts(client):
    make_post("Feed me")

    response = client.get("/blog/feed/")

    assert response.status_code == 200
    assert b"Feed me" in response.content
    assert b"<rss" in response.content


def test_the_feed_excludes_drafts(client):
    make_post("Draft post", published=False)

    assert b"Draft post" not in client.get("/blog/feed/").content


def test_the_listing_advertises_the_feed(client):
    assert b'type="application/rss+xml"' in client.get("/blog/").content


# --- performance -------------------------------------------------------------


def test_a_full_listing_page_costs_a_fixed_number_of_queries(
    client, django_assert_max_num_queries
):
    """Author, category and tags are prefetched, so twelve posts is not
    forty queries.

    The budget includes one query for `tracking_settings`, the site-wide
    tag configuration every public page now reads to decide whether
    GTM/GA4/Pixel/RudderStack snippets render.
    """
    category = make_category("Strategy")
    tag = make_tag("SEO")
    for index in range(12):
        make_post(f"Post {index}", category=category, tags=[tag],
                  published_at=timezone.now() - timedelta(hours=index))

    with django_assert_max_num_queries(15):
        assert client.get("/blog/").status_code == 200


def test_a_byline_never_exposes_a_staff_email(client):
    """`get_full_name()` falls back to the email address, which would put
    a staff member's email on the public site."""
    from apps.accounts.tests.factories import make_user

    author = make_user(email="private@heliograph.agency", full_name="")
    make_post("Anonymous", author=author)

    body = client.get("/blog/anonymous/").content

    assert b"private@heliograph.agency" not in body


def test_a_byline_uses_the_authors_name_when_set(client):
    from apps.accounts.tests.factories import make_user

    author = make_user(email="writer@heliograph.agency", full_name="Sam Writer")
    make_post("Credited", author=author)

    assert b"Sam Writer" in client.get("/blog/credited/").content


def test_the_listing_never_exposes_a_staff_email(client):
    from apps.accounts.tests.factories import make_user

    author = make_user(email="private@heliograph.agency", full_name="")
    make_post("Listed", author=author)

    assert b"private@heliograph.agency" not in client.get("/blog/").content


def test_search_matches_published_copy_and_keeps_drafts_private(client):
    from apps.cms.models import BlogPost

    title_match = make_post("Attribution explained")
    body_match = make_post("A measurement guide", content="Practical attribution advice.")
    excerpt_match = make_post("A useful resource", excerpt="Attribution essentials")
    make_post("Attribution draft", published=False)
    make_post("Attribution tomorrow", published_at=timezone.now() + timedelta(days=1))
    make_post("Unrelated subject")

    response = client.get("/blog/", {"q": "attribution"})

    assert response.status_code == 200
    assert set(response.context["posts"]) == {title_match, body_match, excerpt_match}
    assert BlogPost.objects.count() == 6


def test_search_stays_within_the_selected_category(client):
    first = make_category("First")
    second = make_category("Second")
    wanted = make_post("Search inside this category", category=first)
    make_post("Search outside this category", category=second)

    response = client.get(first.get_absolute_url(), {"q": "search"})

    assert list(response.context["posts"]) == [wanted]


def test_search_pagination_preserves_the_query(client):
    for number in range(13):
        make_post(f"Searchable insight {number}")

    first = client.get("/blog/", {"q": "Searchable"})
    second = client.get("/blog/", {"q": "Searchable", "page": 2})

    assert b'?q=Searchable&amp;page=2' in first.content
    assert second.context["page_obj"].number == 2
    assert len(second.context["posts"]) == 1


def test_search_is_bounded_and_escaped_in_the_form(client):
    response = client.get("/blog/", {"q": '<script>alert("hello")</script>' + "a" * 220})

    assert response.status_code == 200
    assert len(response.context["search"]) == 200
    assert b'<script>alert("hello")</script>' not in response.content
    assert b'&lt;script&gt;' in response.content
