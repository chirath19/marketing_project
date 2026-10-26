"""Pages and the sections they are built from."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.cms.models.site import OrderedVisibleModel, PublishStatus, SiteSettings, Tone
from apps.cms.sections import SECTION_CHOICES, get_section_type
from apps.core.models import TimeStampedModel

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class PageKind(models.TextChoices):
    """Pages the site needs by name, plus everything else.

    The named kinds are routed directly, so the home page is not found by
    guessing at a slug.
    """

    HOME = "home", _("Home")
    ABOUT = "about", _("About")
    CONTACT = "contact", _("Contact")
    SERVICES = "services", _("Services introduction")
    STANDARD = "standard", _("Standard page")


class PageQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=PublishStatus.PUBLISHED)

    def with_sections(self):
        return self.prefetch_related("sections__items")


class Page(TimeStampedModel):
    title = models.CharField(_("title"), max_length=150)
    slug = models.SlugField(_("slug"), max_length=160, unique=True)
    kind = models.CharField(_("kind"), max_length=20, choices=PageKind.choices,
                            default=PageKind.STANDARD, db_index=True)

    status = models.CharField(_("status"), max_length=20,
                              choices=PublishStatus.choices,
                              default=PublishStatus.DRAFT, db_index=True)
    published_at = models.DateTimeField(_("published"), null=True, blank=True)

    # SEO. Each falls back to the page title or the site default rather
    # than rendering empty.
    meta_title = models.CharField(
        _("search engine title"), max_length=70, blank=True,
        help_text=_("Defaults to the page title. About 60 characters."),
    )
    meta_description = models.CharField(
        _("meta description"), max_length=180, blank=True,
        help_text=_("About 155 characters. Written for a person, not a crawler."),
    )
    og_image = models.ImageField(_("social share image"),
                                 upload_to="cms/social/", blank=True)
    noindex = models.BooleanField(
        _("hide from search engines"), default=False,
        help_text=_("Adds a noindex tag. For thank-you pages and the like."),
    )

    objects = PageQuerySet.as_manager()

    class Meta:
        verbose_name = _("page")
        verbose_name_plural = _("pages")
        ordering = ["title"]
        indexes = [
            models.Index(fields=["status", "kind"], name="page_status_kind_idx"),
        ]
        constraints = [
            # One home page, one about page, one contact page. A second
            # would make "the home page" ambiguous.
            models.UniqueConstraint(
                fields=["kind"],
                condition=models.Q(kind__in=["home", "about", "contact"]),
                name="unique_page_per_named_kind",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        if self.kind == PageKind.HOME:
            return reverse("public:home")
        if self.kind == PageKind.CONTACT:
            return reverse("public:contact")
        if self.kind == PageKind.SERVICES:
            return reverse("public:services")
        return reverse("public:page", kwargs={"slug": self.slug})

    @property
    def is_published(self) -> bool:
        return self.status == PublishStatus.PUBLISHED

    def resolved_meta_title(self, site: SiteSettings) -> str:
        return self.meta_title or self.title or site.default_meta_title

    def resolved_meta_description(self, site: SiteSettings) -> str:
        return self.meta_description or site.default_meta_description


class PageSection(OrderedVisibleModel):
    """One block on a page, of a predefined type.

    The fields are a superset; which of them a type uses is declared in
    `sections.py`, and `clean()` refuses a section missing one its type
    requires — so a half-filled section cannot reach the public site.
    """

    page = models.ForeignKey(Page, on_delete=models.CASCADE,
                             related_name="sections", verbose_name=_("page"))
    section_type = models.CharField(_("type"), max_length=40,
                                    choices=SECTION_CHOICES, db_index=True)

    eyebrow = models.CharField(_("eyebrow"), max_length=80, blank=True,
                               help_text=_("Small line above the heading."))
    heading = models.CharField(_("heading"), max_length=200, blank=True)
    subheading = models.CharField(_("subheading"), max_length=300, blank=True)
    body = models.TextField(
        _("body"), blank=True,
        help_text=_("Plain text. Blank lines separate paragraphs. "
                    "**bold**, *italic*, - list, > quote, [text](link) — "
                    "the same formatting as a blog post."),
    )

    image = models.ImageField(_("image"), upload_to="cms/sections/", blank=True)
    image_alt = models.CharField(
        _("image description"), max_length=200, blank=True,
        help_text=_("What the image shows, for people who cannot see it. "
                    "Leave blank only if the image is decorative."),
    )

    cta_label = models.CharField(_("button text"), max_length=60, blank=True)
    cta_url = models.CharField(_("button link"), max_length=300, blank=True)
    secondary_cta_label = models.CharField(_("second button text"), max_length=60,
                                           blank=True)
    secondary_cta_url = models.CharField(_("second button link"), max_length=300,
                                         blank=True)

    tone = models.CharField(_("background"), max_length=10, choices=Tone.choices,
                            default=Tone.LIGHT)
    columns = models.PositiveSmallIntegerField(
        _("columns"), default=3,
        choices=[(2, "2"), (3, "3"), (4, "4")],
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("page section")
        verbose_name_plural = _("page sections")
        indexes = [
            models.Index(fields=["page", "order"], name="section_page_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.page}: {self.get_section_type_display()}"

    def clean(self) -> None:
        section_type = get_section_type(self.section_type)
        if section_type is None:
            raise ValidationError({"section_type": _("Unknown section type.")})

        missing = {
            field: _("This section type needs this field.")
            for field in section_type.required
            if not getattr(self, field, None)
        }
        if missing:
            raise ValidationError(missing)

        if self.image and not self.image_alt:
            raise ValidationError({
                "image_alt": _("Describe the image, or remove it. An image with "
                               "no description is invisible to anyone using a "
                               "screen reader."),
            })

    @property
    def type_config(self):  # noqa: ANN201
        return get_section_type(self.section_type)

    @property
    def template_name(self) -> str:
        from apps.cms.sections import template_for

        return template_for(self.section_type)

    @property
    def paragraphs(self) -> list[str]:
        """Body text split into paragraphs, so templates need no filter.

        Kept for sections that want plain paragraphs. Anything an editor
        might format should render `body_html` instead.
        """
        return [block.strip() for block in self.body.split("\n\n") if block.strip()]

    @property
    def anchor(self) -> str:
        """A stable in-page address for this section.

        Derived from the heading so a link can point at
        `/privacy/#cookies-and-tracking` and land where a reader expects.
        Falls back to the row id for a section with no heading, which is
        less memorable but never collides and never breaks.
        """
        from django.utils.text import slugify

        return slugify(self.heading)[:60] or f"section-{self.pk}"

    @property
    def body_html(self) -> str:
        """The body, run through the site's own formatter.

        The same escape-first renderer blog posts use, so an editor who
        learns the formatting in one place can use it in the other.
        Before this existed a section body printed `**like this**`
        literally, which is a strange thing for a content system to do to
        somebody who followed its own conventions elsewhere.
        """
        from apps.cms.richtext import render

        return render(self.body)


class SectionItem(OrderedVisibleModel):
    """A repeating row inside a section — one feature, one statistic."""

    section = models.ForeignKey(PageSection, on_delete=models.CASCADE,
                                related_name="items", verbose_name=_("section"))
    label = models.CharField(_("label"), max_length=120, blank=True,
                             help_text=_("For a statistic, the thing measured."))
    value = models.CharField(_("value"), max_length=120, blank=True,
                             help_text=_("For a statistic, the number."))
    body = models.TextField(_("description"), blank=True)
    icon = models.CharField(_("icon"), max_length=8, blank=True,
                            help_text=_("A single character or emoji. Decorative."))

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("section item")
        verbose_name_plural = _("section items")
        indexes = [
            models.Index(fields=["section", "order"], name="item_section_order_idx"),
        ]

    def __str__(self) -> str:
        return self.label or self.value or f"Item {self.pk}"
