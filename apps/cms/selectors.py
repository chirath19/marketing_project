"""Read access for the CMS.

Public reads and admin reads are separated on purpose. A published page
and a draft are fetched by different functions, so a preview URL can never
be the same code path as the live site.
"""

from __future__ import annotations

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from apps.cms.models import (
    FAQ,
    BannerPlacement,
    ContactPoint,
    NavigationItem,
    Page,
    PageKind,
    PageSection,
    PromoBanner,
    SectionItem,
    SiteSettings,
    SocialLink,
    TeamMember,
    Testimonial,
)


def site_settings() -> SiteSettings:
    return SiteSettings.objects.current()


def _page_base() -> QuerySet:
    """A page with its visible sections and their items, in one go.

    Hidden sections and hidden items are filtered in the prefetch rather
    than in the template, so the public page costs the same two queries
    however much is hidden.
    """
    return Page.objects.prefetch_related(
        Prefetch(
            "sections",
            queryset=PageSection.objects.visible().order_by("order", "pk")
            .prefetch_related(
                Prefetch("items",
                         queryset=SectionItem.objects.visible().order_by("order", "pk"))
            ),
        )
    )


def published_page(slug: str):  # noqa: ANN201
    return _page_base().published().filter(slug=slug).first()


def services_intro_page():  # noqa: ANN201
    """The editable introduction the service catalogue renders above its grid.

    Named rather than leaving the catalogue to ask for a page "of kind
    services": that would mean the catalogue importing this domain's
    PageKind, and the layering rule exists precisely so one domain
    cannot start depending on another's enumerations.
    """
    return published_page_of_kind(PageKind.SERVICES)


def published_page_of_kind(kind: str):  # noqa: ANN201
    return _page_base().published().filter(kind=kind).first()


def home_page():  # noqa: ANN201
    return published_page_of_kind(PageKind.HOME)


def published_pages() -> QuerySet:
    """Every live page. Used by the sitemap."""
    return Page.objects.published().exclude(noindex=True).order_by("title")


# --- shared collections ----------------------------------------------------


def visible_testimonials() -> QuerySet:
    return Testimonial.objects.visible()


def visible_team() -> QuerySet:
    return TeamMember.objects.visible()


def visible_faqs() -> QuerySet:
    return FAQ.objects.visible()


def collection_for(key: str) -> QuerySet | None:
    """The shared collection a section type draws on."""
    return {
        "testimonials": visible_testimonials,
        "team": visible_team,
        "faqs": visible_faqs,
    }.get(key, lambda: None)()


# --- chrome ----------------------------------------------------------------


def navigation(placement: str) -> QuerySet:
    return (
        NavigationItem.objects.visible()
        .filter(placement=placement)
        .select_related("page")
        .order_by("order", "pk")
    )


def live_banner(*, is_home: bool):  # noqa: ANN201
    """The banner to show, if any.

    Dates are applied in the query so an expired banner never reaches the
    template, and only the first is returned — two announcement strips at
    once is one too many.
    """
    now = timezone.now()
    placements = [BannerPlacement.SITE_TOP]
    if is_home:
        placements.append(BannerPlacement.HOME_ONLY)

    started = Q(starts_at__isnull=True) | Q(starts_at__lte=now)
    not_ended = Q(ends_at__isnull=True) | Q(ends_at__gt=now)

    return (
        PromoBanner.objects.visible()
        .filter(placement__in=placements)
        .filter(started & not_ended)
        .order_by("order", "pk")
        .first()
    )


def visible_social_links() -> QuerySet:
    return SocialLink.objects.visible()


# ---------------------------------------------------------------------------
# Blog
# ---------------------------------------------------------------------------


def published_posts() -> QuerySet:
    """Live posts, newest first, ready to list.

    `for_listing` brings the author, category and tags along, so a page of
    twelve posts is a fixed handful of queries rather than forty.
    """
    from apps.cms.models import BlogPost

    return BlogPost.objects.published().for_listing()


def published_post(slug: str):  # noqa: ANN201
    from apps.cms.models import BlogPost

    return (
        BlogPost.objects.published()
        .select_related("category", "author")
        .prefetch_related("tags")
        .filter(slug=slug)
        .first()
    )


def posts_in_category(slug: str) -> QuerySet:
    return published_posts().filter(category__slug=slug)


def posts_with_tag(slug: str) -> QuerySet:
    return published_posts().filter(tags__slug=slug)


def visible_categories() -> QuerySet:
    """Categories that have at least one live post.

    A category page with nothing on it is a dead end for a visitor and a
    thin page for a crawler, so empty ones are not offered.
    """
    from django.db.models import Count, Q
    from django.utils import timezone

    from apps.cms.models import Category, PublishStatus

    return (
        Category.objects.visible()
        .annotate(post_count=Count(
            "posts",
            filter=Q(posts__status=PublishStatus.PUBLISHED,
                     posts__published_at__lte=timezone.now()),
            distinct=True,
        ))
        .filter(post_count__gt=0)
        .order_by("order", "name")
    )


def visible_tags() -> QuerySet:
    from django.db.models import Count, Q
    from django.utils import timezone

    from apps.cms.models import PublishStatus, Tag

    return (
        Tag.objects.visible()
        .annotate(post_count=Count(
            "posts",
            filter=Q(posts__status=PublishStatus.PUBLISHED,
                     posts__published_at__lte=timezone.now()),
            distinct=True,
        ))
        .filter(post_count__gt=0)
        .order_by("name")
    )


def related_posts(post, *, limit: int = 3) -> list:  # noqa: ANN001
    """Posts a reader of this one is likely to want next.

    Same category first, because that is the strongest signal. If that
    does not fill the row, posts sharing a tag are added. Never the post
    itself, and never a draft.

    Returns a list rather than a queryset: it is the union of two
    different queries, and a caller only ever iterates it.
    """
    chosen: list = []
    seen = {post.pk}

    if post.category_id:
        chosen.extend(
            published_posts().filter(category_id=post.category_id)
            .exclude(pk=post.pk)[:limit]
        )
        seen.update(item.pk for item in chosen)

    if len(chosen) < limit:
        tag_ids = list(post.tags.values_list("pk", flat=True))
        if tag_ids:
            chosen.extend(
                published_posts().filter(tags__in=tag_ids)
                .exclude(pk__in=seen)
                .distinct()[: limit - len(chosen)]
            )

    return chosen[:limit]


def visible_contacts():
    return ContactPoint.objects.visible().order_by("order", "pk")
