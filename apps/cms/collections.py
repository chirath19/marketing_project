"""The CMS collections the staff dashboard can edit.

One declarative registry instead of eight near-identical CRUD screens.
Each entry says what the model is, which form edits it, and what the list
shows; a pair of generic views does the rest.

Adding a collection — blog posts, case studies — is an entry here plus a
form. No new views, no new templates, and the permission checks come
along for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.catalog.forms import ServiceCategoryForm
from apps.catalog.models import ServiceCategory
from apps.cms import forms as cms_forms
from apps.cms.models import (
    FAQ,
    Category,
    ContactPoint,
    NavigationItem,
    PromoBanner,
    SocialLink,
    Tag,
    TeamMember,
    Testimonial,
)


@dataclass(frozen=True, slots=True)
class Collection:
    key: str
    label: str
    singular: str
    model: Any
    form: Any
    #: (heading, attribute) pairs for the list table.
    columns: tuple[tuple[str, str], ...]
    description: str = ""
    #: What an editor should know when the list is empty: what the
    #: entries are for, and where they will show up once added. The
    #: description above says what the list is; this says why it is
    #: worth filling in.
    empty_hint: str = ""
    #: Rows the admin can reorder. Everything ordered on the public site.
    orderable: bool = True
    select_related: tuple[str, ...] = field(default_factory=tuple)


COLLECTIONS: tuple[Collection, ...] = (
    Collection(
        key="contacts", label="Additional contacts", singular="contact",
        model=ContactPoint, form=cms_forms.ContactPointForm,
        columns=(("Label", "label"), ("Type", "get_kind_display"), ("Details", "value")),
        description="Extra email addresses, phone numbers, offices and opening hours.",
        empty_hint=("Add a contact to display alongside your primary details on pages "
                    "with a Contact details section."),
    ),
    Collection(
        key="testimonials", label="Testimonials", singular="testimonial",
        model=Testimonial, form=cms_forms.TestimonialForm,
        columns=(("Who", "author_name"), ("Company", "company"),
                 ("Quote", "quote")),
        description="Shown by any page with a testimonials section.",
        empty_hint=(
            "A testimonial appears on any page carrying a testimonials section, "
            "and the section hides itself while this list is empty — so the page "
            "never shows a heading with nothing under it. Add only quotes you "
            "have permission to publish."
        ),
    ),
    Collection(
        key="team", label="Team", singular="team member",
        model=TeamMember, form=cms_forms.TeamMemberForm,
        columns=(("Name", "name"), ("Role", "role")),
        description="Shown by any page with a team section.",
        empty_hint=(
            "Team members appear on any page carrying a team section, and that "
            "section stays hidden until somebody is listed here. A photo is "
            "optional; a role is what readers actually look for."
        ),
    ),
    Collection(
        key="faqs", label="Questions and answers", singular="question",
        model=FAQ, form=cms_forms.FAQForm,
        columns=(("Question", "question"), ("Group", "category")),
        description="Shown by any page with a questions section.",
        empty_hint=(
            "Questions appear on any page carrying a questions section. Answer "
            "them against what the business genuinely does — these set "
            "expectations a client will later hold you to."
        ),
    ),
    Collection(
        key="banners", label="Promotional banners", singular="banner",
        model=PromoBanner, form=cms_forms.PromoBannerForm,
        columns=(("Message", "message"), ("Placement", "get_placement_display")),
        description="A strip above the header. Dated, so it takes itself down.",
        empty_hint=(
            "A banner runs as a strip above the site header. Give it an end date "
            "and it takes itself down, so an announcement about a deadline cannot "
            "outlive the deadline."
        ),
    ),
    Collection(
        key="navigation", label="Navigation", singular="navigation item",
        model=NavigationItem, form=cms_forms.NavigationItemForm,
        columns=(("Label", "label"), ("Placement", "get_placement_display"),
                 ("Goes to", "href")),
        description="Header and footer links.",
        select_related=("page",),
        empty_hint=(
            "Links here build the header and the footer columns. Nothing in the "
            "site chrome is hard-coded, so a page with no navigation item is "
            "reachable only by its address."
        ),
    ),
    Collection(
        key="blog-categories", label="Blog categories", singular="category",
        model=Category, form=cms_forms.CategoryForm,
        columns=(("Name", "name"), ("Description", "description")),
        description="One per post. Each gets its own page on the site.",
        empty_hint=(
            "Every article belongs to one category, and each category gets its "
            "own page and listing on the public site."
        ),
    ),
    Collection(
        key="blog-tags", label="Blog tags", singular="tag",
        model=Tag, form=cms_forms.TagForm,
        columns=(("Name", "name"), ("Slug", "slug")),
        description="Cross-cutting labels. A post can carry several.",
        empty_hint=(
            "Tags cut across categories. An article can carry several, and each "
            "tag gets its own listing page."
        ),
    ),
    Collection(
        key="service-categories", label="Service categories", singular="category",
        model=ServiceCategory, form=ServiceCategoryForm,
        columns=(("Name", "name"), ("Description", "short_description")),
        description="How the catalogue is grouped — Search, Paid, Social, Email.",
        empty_hint=(
            "Categories group the service catalogue and become its filter "
            "buttons. A service cannot be published without one."
        ),
    ),
    Collection(
        key="social", label="Social links", singular="social link",
        model=SocialLink, form=cms_forms.SocialLinkForm,
        columns=(("Platform", "get_platform_display"), ("Link", "url")),
        description="Shown in the footer and in the site's structured data.",
        empty_hint=(
            "Social links appear in the footer and in the site's structured data, "
            "which is what search engines read to connect the site to your "
            "profiles."
        ),
    ),
)

COLLECTIONS_BY_KEY: dict[str, Collection] = {
    collection.key: collection for collection in COLLECTIONS
}


def get_collection(key: str) -> Collection | None:
    return COLLECTIONS_BY_KEY.get(key)
