"""Sitemap for the public site.

Only published pages that are not marked noindex: telling a crawler about
a page and then asking it not to index that page is a mixed signal worth
avoiding.
"""

from django.contrib.sitemaps import Sitemap

from apps.cms import selectors
from apps.cms.models import PageKind


class PageSitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        return selectors.published_pages()

    def location(self, item):  # noqa: ANN001
        return item.get_absolute_url()

    def lastmod(self, item):  # noqa: ANN001
        return item.updated_at

    def priority(self, item):  # noqa: ANN001
        # The home page is the one a crawler should weight most.
        return 1.0 if item.kind == PageKind.HOME else 0.6


class BlogPostSitemap(Sitemap):
    changefreq = "monthly"
    protocol = "https"

    def items(self):
        return selectors.published_posts()

    def location(self, item):  # noqa: ANN001
        return item.get_absolute_url()

    def lastmod(self, item):  # noqa: ANN001
        return item.updated_at

    def priority(self, item):  # noqa: ANN001
        return 0.7


class BlogCategorySitemap(Sitemap):
    changefreq = "weekly"
    protocol = "https"

    def items(self):
        # Only categories with something on them: an empty page is a dead
        # end for a visitor and a thin page for a crawler.
        return selectors.visible_categories()

    def location(self, item):  # noqa: ANN001
        return item.get_absolute_url()

    def priority(self, item):  # noqa: ANN001
        return 0.4


SITEMAPS = {
    "pages": PageSitemap,
    "posts": BlogPostSitemap,
    "blog-categories": BlogCategorySitemap,
}
