"""The section types a page can be built from.

Deliberately a closed set. A drag-and-drop builder lets anyone produce a
page that looks nothing like the rest of the site; a fixed vocabulary of
well-made sections keeps every page on brand without the editor having to
think about layout at all.

Each type declares which fields it uses, which it requires, and whether it
draws on a shared collection (testimonials, team, FAQs) rather than
carrying its own content. The admin form shows only the fields a type
uses, and `PageSection.clean()` enforces the required ones — so a section
cannot be saved half-configured and render broken on the public site.

Adding a type means adding an entry here and a template in
`templates/cms/sections/<key>.html`. Nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Every field a section row can carry. A type opts into the ones it needs.
ALL_FIELDS = (
    "eyebrow", "heading", "subheading", "body",
    "image", "image_alt",
    "cta_label", "cta_url", "secondary_cta_label", "secondary_cta_url",
    "tone", "columns",
)


@dataclass(frozen=True, slots=True)
class SectionType:
    key: str
    label: str
    description: str
    fields: tuple[str, ...]
    required: tuple[str, ...] = ()
    #: Repeating child rows (a feature list, a set of statistics).
    supports_items: bool = False
    item_label: str = "Item"
    #: A shared collection this type pulls from, so the same testimonials
    #: can appear on more than one page without being retyped.
    collection: str = ""


SECTION_TYPES: tuple[SectionType, ...] = (
    SectionType(
        key="hero",
        label="Hero",
        description="The opening statement of a page. One per page, at the top.",
        fields=("eyebrow", "heading", "subheading", "image", "image_alt",
                "cta_label", "cta_url", "secondary_cta_label", "secondary_cta_url",
                "tone"),
        required=("heading",),
    ),
    SectionType(
        key="rich_text",
        label="Text block",
        description="A heading and some prose. For an about page or a policy.",
        fields=("eyebrow", "heading", "body", "tone"),
        required=("body",),
    ),
    SectionType(
        key="feature_grid",
        label="Feature grid",
        description="A short list of what you do, in two to four columns.",
        fields=("eyebrow", "heading", "subheading", "tone", "columns",
                "cta_label", "cta_url"),
        required=("heading",),
        supports_items=True,
        item_label="Feature",
    ),
    SectionType(
        key="stats",
        label="Statistics",
        description="A row of numbers worth leading with.",
        fields=("eyebrow", "heading", "tone", "columns"),
        supports_items=True,
        item_label="Statistic",
    ),
    SectionType(
        key="testimonials",
        label="Testimonials",
        description="Quotes from the shared testimonial list.",
        fields=("eyebrow", "heading", "subheading", "tone"),
        collection="testimonials",
    ),
    SectionType(
        key="team",
        label="Team",
        description="People from the shared team list.",
        fields=("eyebrow", "heading", "subheading", "tone"),
        collection="team",
    ),
    SectionType(
        key="faq",
        label="Questions and answers",
        description="Entries from the shared FAQ list.",
        fields=("eyebrow", "heading", "subheading", "tone"),
        collection="faqs",
    ),
    SectionType(
        key="cta_band",
        label="Call to action",
        description="A full-width band asking the visitor to do one thing.",
        fields=("eyebrow", "heading", "subheading", "cta_label", "cta_url",
                "secondary_cta_label", "secondary_cta_url", "tone"),
        required=("heading", "cta_label", "cta_url"),
    ),
    SectionType(
        key="contact_details",
        label="Contact details",
        description="Email, phone, WhatsApp and address, from site settings. "
                    "Edited in one place so they cannot drift between pages.",
        fields=("eyebrow", "heading", "subheading", "tone"),
    ),
    SectionType(
        key="contact_form",
        label="Contact form",
        description="The enquiry form. Submissions are stored and appear in "
                    "the staff Inbox; nothing is emailed.",
        fields=("eyebrow", "heading", "subheading", "tone"),
    ),
    SectionType(
        key="image_text",
        label="Image and text",
        description="A picture beside a block of prose.",
        fields=("eyebrow", "heading", "body", "image", "image_alt",
                "cta_label", "cta_url", "tone"),
        required=("heading", "image"),
    ),
)

SECTION_TYPES_BY_KEY: dict[str, SectionType] = {
    section.key: section for section in SECTION_TYPES
}

SECTION_CHOICES = [(section.key, section.label) for section in SECTION_TYPES]


def get_section_type(key: str) -> SectionType | None:
    return SECTION_TYPES_BY_KEY.get(key)


def fields_for(key: str) -> tuple[str, ...]:
    section = get_section_type(key)
    return section.fields if section else ()


def required_for(key: str) -> tuple[str, ...]:
    section = get_section_type(key)
    return section.required if section else ()


def template_for(key: str) -> str:
    """The template that renders this type.

    Falls back to a type that renders nothing rather than raising: a
    section type removed from the code should not take the whole public
    page down with it.
    """
    if key in SECTION_TYPES_BY_KEY:
        return f"cms/sections/{key}.html"
    return "cms/sections/_unknown.html"
