"""The public website.

Pages are assembled from their sections and nothing else. There is no
content in these views or their templates — a view that hard-coded a
headline would be a headline the agency could not change.

Every page is two queries: the page with its sections and items
prefetched, and the navigation. Collections used by a section
(testimonials, team, FAQs) add one each, only when a section asks for
them.
"""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control

from apps.cms import selectors
from apps.cms.models import PageKind


def _render_page(request: HttpRequest, page) -> HttpResponse:  # noqa: ANN001
    """Render a CMS page with everything its sections need.

    Collections are resolved here rather than in the template so each is
    fetched once, however many sections draw on it.
    """
    collections: dict[str, object] = {}
    contact_form = None
    sections = []
    # Picture-and-text sections alternate sides down the page, so two of
    # them in a row do not read as a column of identical rows. Counted
    # here because only this loop knows which sections actually survive
    # to be rendered — an editor's `order` values are multiples of ten,
    # which is to say always even, and deciding from those put every
    # picture on the same side.
    picture_sections = 0

    for section in page.sections.all():
        config = section.type_config
        if config and config.collection:
            if config.collection not in collections:
                collections[config.collection] = selectors.collection_for(
                    config.collection
                )
            # A section backed by an empty collection is left out
            # entirely. Rendering it would put a heading on the page
            # with nothing underneath — the editor placed the section in
            # good faith, but an empty "What our clients say" is worse
            # than no such section at all.
            if not collections[config.collection]:
                continue

        if section.section_type == "image_text":
            section.image_on_right = bool(picture_sections % 2)
            picture_sections += 1

        sections.append(section)

        if section.section_type == "contact_form" and contact_form is None:
            # Built here rather than in the template so the honeypot's
            # signed timestamp is generated once, on render.
            from apps.leads.forms import ContactForm

            contact_form = ContactForm()

    site = selectors.site_settings()
    is_home = page.kind == PageKind.HOME

    return render(request, "public/page.html", {
        "page": page,
        "sections": sections,
        "collections": collections,
        "is_home": is_home,
        "banner": selectors.live_banner(is_home=is_home),
        # Resolved here, not in the template: the fallback chain is
        # page → site default → page title, and a template cannot call a
        # method that takes an argument.
        "contact_form": contact_form,
        "meta_title": page.resolved_meta_title(site),
        "meta_description": page.resolved_meta_description(site),
    })


def home(request: HttpRequest) -> HttpResponse:
    page = selectors.home_page()
    if page is None:
        raise Http404("No published home page.")
    return _render_page(request, page)


def page_detail(request: HttpRequest, slug: str) -> HttpResponse:
    page = selectors.published_page(slug)
    if page is None:
        raise Http404("No published page with that address.")
    return _render_page(request, page)


def contact_page(request: HttpRequest) -> HttpResponse:
    """The contact page, routed by kind rather than by slug.

    So that renaming its slug cannot break the link the site relies on.
    """
    page = selectors.published_page_of_kind(PageKind.CONTACT)
    if page is None:
        raise Http404("No published contact page.")
    return _render_page(request, page)


@cache_control(max_age=60 * 60 * 24)
def robots_txt(request: HttpRequest) -> HttpResponse:
    """Points crawlers at the sitemap and keeps them out of private areas.

    Not a security control — anything genuinely private is refused by the
    server regardless. This simply stops the dashboard and the API filling
    up a search index.
    """
    sitemap = request.build_absolute_uri("/sitemap.xml")
    lines = [
        "User-agent: *",
        "Disallow: /staff/",
        "Disallow: /organization/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "Disallow: /admin/",
        "",
        f"Sitemap: {sitemap}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
