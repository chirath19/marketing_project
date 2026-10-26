"""Test helpers for CMS content."""

from __future__ import annotations

from apps.cms.models import (
    FAQ,
    NavigationItem,
    Page,
    PageSection,
    PublishStatus,
    SectionItem,
    SiteSettings,
    SocialLink,
    TeamMember,
    Testimonial,
)

__all__ = ["make_page", "make_section", "make_item", "make_testimonial",
           "make_team_member", "make_faq", "make_nav_item", "make_social_link",
           "site_settings"]


def site_settings(**fields) -> SiteSettings:
    row = SiteSettings.objects.current()
    for name, value in fields.items():
        setattr(row, name, value)
    if fields:
        row.save()
    return row


def make_page(title: str = "Test page", *, slug: str = "", kind: str = "standard",
              status: str = PublishStatus.PUBLISHED, **fields) -> Page:
    return Page.objects.create(
        title=title, slug=slug or title.lower().replace(" ", "-"),
        kind=kind, status=status, **fields,
    )


def make_section(page: Page, section_type: str = "rich_text", **fields) -> PageSection:
    defaults = {"body": "Some words.", "order": 10}
    defaults.update(fields)
    return PageSection.objects.create(page=page, section_type=section_type, **defaults)


def make_item(section: PageSection, **fields) -> SectionItem:
    return SectionItem.objects.create(section=section, **fields)


def make_testimonial(**fields) -> Testimonial:
    defaults = {"quote": "They were good.", "author_name": "A Client"}
    defaults.update(fields)
    return Testimonial.objects.create(**defaults)


def make_team_member(**fields) -> TeamMember:
    defaults = {"name": "A Person"}
    defaults.update(fields)
    return TeamMember.objects.create(**defaults)


def make_faq(**fields) -> FAQ:
    defaults = {"question": "How much?", "answer": "It depends."}
    defaults.update(fields)
    return FAQ.objects.create(**defaults)


def make_nav_item(**fields) -> NavigationItem:
    defaults = {"label": "Services", "url": "/services/", "placement": "header"}
    defaults.update(fields)
    return NavigationItem.objects.create(**defaults)


def make_social_link(**fields) -> SocialLink:
    defaults = {"platform": "linkedin", "url": "https://linkedin.com/company/x"}
    defaults.update(fields)
    return SocialLink.objects.create(**defaults)


def make_category(name: str = "Strategy", **fields):  # noqa: ANN201
    from django.utils.text import slugify

    from apps.cms.models import Category

    defaults = {"slug": slugify(name)}
    defaults.update(fields)
    return Category.objects.create(name=name, **defaults)


def make_tag(name: str = "SEO", **fields):  # noqa: ANN201
    from django.utils.text import slugify

    from apps.cms.models import Tag

    defaults = {"slug": slugify(name)}
    defaults.update(fields)
    return Tag.objects.create(name=name, **defaults)


def make_post(title: str = "A post", *, published: bool = True, **fields):  # noqa: ANN201
    from django.utils import timezone
    from django.utils.text import slugify

    from apps.cms.models import BlogPost, PublishStatus

    defaults = {
        "slug": slugify(title),
        "content": "An opening paragraph.\n\nAnd a second one.",
        "status": PublishStatus.PUBLISHED if published else PublishStatus.DRAFT,
        "published_at": timezone.now() if published else None,
    }
    tags = fields.pop("tags", None)
    defaults.update(fields)
    post = BlogPost.objects.create(title=title, **defaults)
    if tags:
        post.tags.set(tags)
    return post
