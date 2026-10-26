"""CMS editing forms.

`PageSectionForm` is the one with real work in it: a section's type
decides which fields apply, so the form shows only those. An editor
choosing "Testimonials" should not be looking at a button-link field that
type ignores.
"""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.urls import Resolver404, resolve
from django.utils.translation import gettext_lazy as _

from apps.cms.models import (
    FAQ,
    BlogPost,
    Category,
    ContactPoint,
    NavigationItem,
    Page,
    PageSection,
    PromoBanner,
    SectionItem,
    SiteSettings,
    SocialLink,
    Tag,
    TeamMember,
    Testimonial,
)
from apps.cms.sections import SECTION_CHOICES, fields_for, required_for
from apps.core.forms import StyledModelForm


class SiteSettingsForm(StyledModelForm):
    class Meta:
        model = SiteSettings
        exclude = ["created_at", "updated_at"]


class ContactSettingsForm(StyledModelForm):
    class Meta:
        model = SiteSettings
        fields = ["contact_email", "contact_phone", "whatsapp_number", "whatsapp_message",
                  "address_line1", "address_line2", "city", "postal_code", "country",
                  "response_time_note"]


class ContactPointForm(StyledModelForm):
    class Meta:
        model = ContactPoint
        fields = ["label", "kind", "value", "description", "link", "is_visible"]
        widgets = {"value": forms.Textarea(attrs={"rows": 3})}


class PageForm(StyledModelForm):
    class Meta:
        model = Page
        fields = ["title", "slug", "kind", "meta_title", "meta_description",
                  "og_image", "noindex"]
        help_texts = {
            "slug": _("The address this page lives at. Changing it breaks "
                      "existing links."),
        }

    def clean(self):
        data = super().clean()
        slug = data.get("slug")
        if slug:
            try:
                route = resolve(f"/{slug}/").view_name
            except Resolver404:
                route = "public:page"
            allowed = {"public:page"}
            if data.get("kind") == "contact":
                allowed.add("public:contact")
            if data.get("kind") == "services":
                allowed.add("public:services")
            if route not in allowed:
                self.add_error("slug", "This address is already in use. Choose another.")
        return data


class PageSectionForm(StyledModelForm):
    """A section, showing only the fields its type uses.

    The type is fixed once the section exists: changing it would leave
    content in fields the new type does not render, which looks like data
    loss to whoever typed it. Delete and add instead.
    """

    class Meta:
        model = PageSection
        fields = ["section_type", "eyebrow", "heading", "subheading", "body",
                  "image", "image_alt", "cta_label", "cta_url",
                  "secondary_cta_label", "secondary_cta_url", "tone", "columns",
                  "is_visible"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        instance = kwargs.get("instance") or self.instance
        chosen = instance.section_type if instance.pk else (
            self.data.get("section_type") or self.initial.get("section_type", "")
        )

        if instance and instance.pk:
            self.fields["section_type"].disabled = True
            self.fields["section_type"].help_text = _(
                "Fixed once a section exists. Delete and add a new one to "
                "change the shape."
            )
        else:
            self.fields["section_type"].choices = [("", _("Choose a type"))] + list(
                SECTION_CHOICES
            )

        if chosen:
            used = set(fields_for(chosen))
            for name in list(self.fields):
                if name in {"section_type", "is_visible"}:
                    continue
                if name == "image_alt" and "image" in used:
                    continue
                if name not in used:
                    del self.fields[name]

            for name in required_for(chosen):
                if name in self.fields:
                    self.fields[name].required = True

    def clean(self):
        data = super().clean()
        for name in ("cta_url", "secondary_cta_url"):
            url = data.get(name)
            if not url:
                continue
            if not any(char.isspace() or ord(char) < 32 for char in url) and (
                url.startswith("#") or (url.startswith("/") and not url.startswith("//")
                                         and "\\" not in url)
            ):
                continue
            try:
                URLValidator(schemes=["http", "https"])(url)
            except ValidationError:
                self.add_error(name, "Use a path like /contact/, an #anchor, or an https:// URL.")
        return data


class SectionItemForm(StyledModelForm):
    class Meta:
        model = SectionItem
        fields = ["label", "value", "body", "icon", "is_visible"]

    def __init__(self, *args, section=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if section is None and self.instance.pk:
            section = self.instance.section
        if section is not None and section.section_type == "feature_grid":
            self.fields.pop("value")
            self.fields["label"].help_text = "The feature or process-step heading."
        elif section is not None and section.section_type == "stats":
            self.fields.pop("icon")


class TestimonialForm(StyledModelForm):
    class Meta:
        model = Testimonial
        fields = ["quote", "author_name", "author_role", "company", "photo",
                  "is_visible"]


class TeamMemberForm(StyledModelForm):
    class Meta:
        model = TeamMember
        fields = ["name", "role", "bio", "photo", "linkedin_url", "is_visible"]


class FAQForm(StyledModelForm):
    class Meta:
        model = FAQ
        fields = ["question", "answer", "category", "is_visible"]


class PromoBannerForm(StyledModelForm):
    class Meta:
        model = PromoBanner
        fields = ["message", "cta_label", "cta_url", "placement", "tone",
                  "starts_at", "ends_at", "is_visible"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class NavigationItemForm(StyledModelForm):
    class Meta:
        model = NavigationItem
        fields = ["label", "placement", "page", "url", "opens_in_new_tab",
                  "is_cta", "is_visible"]


class SocialLinkForm(StyledModelForm):
    class Meta:
        model = SocialLink
        fields = ["platform", "url", "label", "is_visible"]


# ---------------------------------------------------------------------------
# Blog
# ---------------------------------------------------------------------------


class BlogPostForm(StyledModelForm):
    """A post.

    The slug is optional: left blank it is derived from the title, which
    is what an author wants the first time. It is shown rather than hidden
    because changing it later breaks existing links, and that is a
    decision someone should make deliberately.
    """

    class Meta:
        model = BlogPost
        fields = ["title", "slug", "excerpt", "content", "featured_image",
                  "featured_image_alt", "category", "tags", "published_at",
                  "meta_title", "meta_description"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 18}),
            "excerpt": forms.Textarea(attrs={"rows": 2}),
            "tags": forms.CheckboxSelectMultiple,
            "published_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["category"].empty_label = _("No category")


class CategoryForm(StyledModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "description", "is_visible"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self) -> str:
        from django.utils.text import slugify

        return self.cleaned_data.get("slug") or slugify(
            self.cleaned_data.get("name", "")
        )[:90]


class TagForm(StyledModelForm):
    class Meta:
        model = Tag
        fields = ["name", "slug", "is_visible"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self) -> str:
        from django.utils.text import slugify

        return self.cleaned_data.get("slug") or slugify(
            self.cleaned_data.get("name", "")
        )[:70]
