"""The blog's RSS feed.

Built with Django's own syndication framework rather than a hand-rolled
template, so the dates, escaping and content types are the ones Django
already gets right.
"""

from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Rss201rev2Feed

from apps.cms import selectors


class BlogFeed(Feed):
    feed_type = Rss201rev2Feed

    def title(self):
        return f"{selectors.site_settings().site_name} — blog"

    def description(self):
        site = selectors.site_settings()
        return site.default_meta_description or site.tagline

    link = "/blog/"

    def items(self):
        # A feed reader wants the recent ones, not the archive.
        return selectors.published_posts()[:20]

    def item_title(self, item):  # noqa: ANN001
        return item.title

    def item_description(self, item):  # noqa: ANN001
        return item.summary

    def item_link(self, item):  # noqa: ANN001
        return item.get_absolute_url()

    def item_pubdate(self, item):  # noqa: ANN001
        return item.published_at

    def item_author_name(self, item):  # noqa: ANN001
        return item.byline or None

    def item_categories(self, item):  # noqa: ANN001
        return [item.category.name] if item.category else []
