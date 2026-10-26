"""Rules about what the site is allowed to say.

Copy is edited constantly and nobody reviews a wording change the way
they review a model change. These tests encode the handful of content
rules that are not matters of taste — a promise the platform cannot
keep, a fabricated figure, or a page that renders a heading with nothing
underneath it — so that breaking one is a test failure rather than
something a visitor finds first.
"""

from __future__ import annotations

import re

import pytest

from apps.catalog.models import Service
from apps.cms.models import FAQ, BlogPost, NavigationItem, Page, PageSection

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def public_quote_option():
    # These copy tests cover the optional anonymous quote page as well.
    from apps.core.models import OperatingSettings
    OperatingSettings.objects.update_or_create(pk=1, defaults={"require_quote_account": False})



#: Every public address a visitor can reach without signing in.
PUBLIC_URLS = [
    "/", "/about/", "/services/", "/blog/", "/contact/", "/contact/enquiry/",
    "/quote/", "/privacy/", "/accounts/login/", "/accounts/register/",
]


def _public_bodies(client):  # noqa: ANN001, ANN202
    """Each public page, as raw HTML."""
    for url in PUBLIC_URLS:
        response = client.get(url)
        assert response.status_code == 200, url
        yield url, response.content.decode()


_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)


def _visible_text(html: str) -> str:
    """What a reader actually sees.

    Attributes are stripped before any copy rule is applied: the word
    "placeholder" is legitimate inside `placeholder="Search"`, and a rule
    that cannot tell markup from prose is a rule nobody will keep.
    """
    return _TAG.sub(" ", _SCRIPT.sub(" ", html))


# ---------------------------------------------------------------------------
# Nothing unfinished reaches a visitor
# ---------------------------------------------------------------------------


#: Wording that means somebody stopped halfway. Matched case-insensitively
#: against the rendered page, not the source, so a stray fixture in the
#: database is caught as readily as a stray template.
PLACEHOLDER_PHRASES = (
    "lorem ipsum",
    "coming soon",
    "todo",
    "tbd",
    "placeholder",
    "sample text",
    "your text here",
    "dummy",
    "xxx",
)


def test_no_public_page_contains_placeholder_copy(client):
    for url, body in _public_bodies(client):
        lowered = _visible_text(body).lower()
        for phrase in PLACEHOLDER_PHRASES:
            assert phrase not in lowered, f"{url} contains {phrase!r}"


def test_no_public_page_renders_an_empty_heading(client):
    """A heading with nothing in it means a section rendered half-built."""
    empty = re.compile(r"<h[1-6][^>]*>\s*</h[1-6]>")

    for url, body in _public_bodies(client):
        assert not empty.search(body), f"{url} has an empty heading"


def test_every_public_page_has_exactly_one_h1(client):
    for url, body in _public_bodies(client):
        count = len(re.findall(r"<h1[\s>]", body))
        assert count == 1, f"{url} has {count} level-one headings"


def test_no_public_page_leaks_unrendered_formatting(client):
    """`**bold**` printed literally means a body was not run through the
    formatter that the editor was told to write for."""
    for url, body in _public_bodies(client):
        assert "**" not in _visible_text(body), f"{url} shows unrendered bold markers"


# ---------------------------------------------------------------------------
# Nothing is promised that the platform cannot keep
# ---------------------------------------------------------------------------


#: There is no outbound email, SMS or messaging in this version. A page
#: that tells somebody to wait for a message is sending them to wait for
#: something that will never arrive.
FALSE_PROMISES = (
    "check your inbox",
    "check your email",
    "we have sent you",
    "we've sent you",
    "a confirmation email",
    "confirmation link",
    "verify your email",
    "click the link we sent",
)


def test_no_public_page_promises_a_message_that_is_never_sent(client):
    for url, body in _public_bodies(client):
        lowered = _visible_text(body).lower()
        for promise in FALSE_PROMISES:
            assert promise not in lowered, f"{url} promises: {promise!r}"


def test_the_success_pages_promise_nothing_automatic(client):
    for url in ("/contact/sent/", "/quote/sent/"):
        body = client.get(url).content.decode().lower()
        assert "no automatic confirmation is sent" in body, url


def test_no_reply_time_is_stated_unless_the_agency_configured_one(client):
    """`response_time_note` ships empty on purpose.

    A turnaround printed on the page is a turnaround somebody has to hit
    at five o'clock on a Friday. It is the owner's promise to make, not
    ours to make for them.
    """
    from apps.cms.selectors import site_settings

    assert site_settings().response_time_note == ""

    pattern = re.compile(r"within (one|1|two|2|24|48) (working day|hour|day)",
                         re.IGNORECASE)
    for url, body in _public_bodies(client):
        assert not pattern.search(_visible_text(body)), f"{url} states a reply time"


def test_a_configured_reply_time_is_shown(client):
    """And when the agency does set one, the page says it."""
    from apps.cms.models import SiteSettings

    settings_row = SiteSettings.objects.get()
    settings_row.response_time_note = "We usually reply within two working days."
    settings_row.save(update_fields=["response_time_note"])

    body = client.get("/contact/enquiry/").content.decode()

    assert "within two working days" in body


# ---------------------------------------------------------------------------
# Nothing is invented
# ---------------------------------------------------------------------------


def test_the_seed_ships_no_testimonials(client):
    """A testimonial has to come from a real client who said it.

    Seeding a persuasive quote from a person who does not exist is the
    one content failure that is not merely sloppy.
    """
    from apps.cms.models import Testimonial

    assert not Testimonial.objects.exists()


def test_a_testimonial_section_with_no_testimonials_renders_nothing(client):
    """So an empty list cannot leave a heading stranded on the page."""
    body = client.get("/").content.decode()

    section = PageSection.objects.filter(section_type="testimonials").first()
    assert section is not None, "the home page should carry the section"
    assert section.heading
    assert section.heading not in body


def test_no_public_page_claims_a_performance_figure(client):
    """Percentages and multipliers attached to results need a real client
    behind them, and there is none."""
    claims = re.compile(
        r"\b\d{2,3}%\s*(increase|more|growth|uplift|improvement)"
        r"|\b\d+x\s*(roi|return|growth)",
        re.IGNORECASE,
    )
    for url, body in _public_bodies(client):
        assert not claims.search(_visible_text(body)), f"{url} claims a result"


# ---------------------------------------------------------------------------
# Every page is reachable and described
# ---------------------------------------------------------------------------


def test_every_navigation_link_resolves(client):
    """A footer link to a page that 404s is the cheapest kind of broken."""
    for item in NavigationItem.objects.visible():
        href = item.href.split("#")[0]
        if not href.startswith("/"):
            continue
        assert client.get(href).status_code == 200, f"{item.label} -> {item.href}"


def test_an_in_page_anchor_has_something_to_land_on(client):
    """Links such as /privacy/#cookies-and-tracking must find their mark."""
    for item in NavigationItem.objects.visible():
        if "#" not in item.href:
            continue
        path, _, fragment = item.href.partition("#")
        body = client.get(path).content.decode()
        assert f'id="{fragment}"' in body, f"{item.href} has no anchor"


def test_every_published_page_has_a_meta_description():
    for page in Page.objects.filter(status="published"):
        assert page.resolved_meta_description(None), page.slug


def test_every_live_service_describes_itself():
    """A catalogue card is not enough to buy from."""
    for service in Service.objects.live():
        assert service.short_description, service.slug
        assert service.full_description, service.slug
        assert service.ideal_for, service.slug
        assert service.deliverables, service.slug
        assert service.process, service.slug


def test_the_questions_answer_what_is_actually_built():
    """Each seeded question has a real answer, not a stub."""
    assert FAQ.objects.visible().count() >= 8
    for faq in FAQ.objects.visible():
        assert len(faq.answer) > 60, faq.question


def test_the_blog_launches_with_something_worth_reading():
    posts = BlogPost.objects.published()

    assert posts.count() >= 3
    for post in posts:
        assert post.excerpt, post.slug
        assert post.meta_description, post.slug
        assert len(post.content) > 1500, f"{post.slug} is a stub"


def test_no_published_article_is_an_unfinished_draft():
    for post in BlogPost.objects.all():
        assert "still being written" not in post.title.lower()
        assert len(post.content) > 200, post.title


# ---------------------------------------------------------------------------
# One site, not two
# ---------------------------------------------------------------------------


def test_no_public_page_contains_a_dead_link(client):
    """`href="#"` is a link somebody meant to finish and did not.

    The signed-in shell carried four of them for several phases, so
    anyone who registered met a different, broken version of the site
    they had just been browsing. A fragment link to a real anchor on the
    same page is fine; a bare `#` is not.
    """
    dead = re.compile(r'href="#"')

    for url, body in _public_bodies(client):
        assert not dead.search(body), f"{url} has a link going nowhere"


def test_every_page_renders_the_same_site_name(client):
    """The brand must survive a view that sets a `site` of its own.

    Django's `LoginView` injects one taken from the request host, which
    shadows the CMS settings row the header and footer are built from.
    When it won, the brand on that page went blank — and only on that
    page, which is the kind of thing nobody notices for a month.
    """
    from apps.cms.selectors import site_settings

    expected = site_settings().site_name

    for url, body in _public_bodies(client):
        match = re.search(r'property="og:site_name" content="([^"]*)"', body)
        assert match, f"{url} has no site name"
        assert match.group(1) == expected, url


def test_the_signed_in_shell_is_the_public_one(client):
    """A client should not meet a second, older version of the site."""
    from apps.cms.models import NavigationItem

    labels = list(
        NavigationItem.objects.visible().filter(placement="header")
        .values_list("label", flat=True)
    )
    assert labels, "the header navigation should be seeded"

    body = client.get("/accounts/login/").content.decode()

    for label in labels:
        assert label in body, f"the sign-in page is missing the {label!r} link"
