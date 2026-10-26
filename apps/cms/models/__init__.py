"""CMS models.

A package rather than one module: site settings, pages and the blog are
three separate concerns and one file holding all of them was getting hard
to read. Django resolves the app label from the package path, so the
model paths (`cms.Page`, `cms.BlogPost`) are unchanged and migrations are
unaffected.
"""

from apps.cms.models.blog import BlogPost, Category, Tag
from apps.cms.models.contacts import ContactPoint
from apps.cms.models.pages import Page, PageKind, PageSection, SectionItem
from apps.cms.models.site import (
    FAQ,
    BannerPlacement,
    NavigationItem,
    NavPlacement,
    OrderedVisibleModel,
    OrderedVisibleQuerySet,
    PromoBanner,
    PublishStatus,
    SiteSettings,
    SocialLink,
    SocialPlatform,
    TeamMember,
    Testimonial,
    Tone,
    WebsiteCopy,
)

__all__ = [
    "ContactPoint", "FAQ", "BannerPlacement", "BlogPost", "Category", "NavPlacement",
    "NavigationItem", "OrderedVisibleModel", "OrderedVisibleQuerySet", "Page",
    "PageKind", "PageSection", "PromoBanner", "PublishStatus", "SectionItem",
    "SiteSettings", "SocialLink", "SocialPlatform", "Tag", "TeamMember",
    "Testimonial", "Tone", "WebsiteCopy",
]
