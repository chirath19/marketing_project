"""Editable website content.

Everything the public site shows that an agency would ever want to change
lives here, not in a template. Changing the phone number, the hero
headline, the order of sections or which testimonials appear is an
editing task, not a deploy.

The structure is deliberately closed: a page is an ordered list of
sections drawn from a fixed vocabulary (`sections.py`). There is no
free-form page builder, because one produces pages that look nothing like
the rest of the site.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class PublishStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")


class Tone(models.TextChoices):
    """The surface a section is drawn on. Brand colours, not free choice."""

    LIGHT = "light", _("White")
    MIST = "mist", _("Mist")
    NAVY = "navy", _("Deep navy")


# ---------------------------------------------------------------------------
# Site-wide settings
# ---------------------------------------------------------------------------


class SiteSettingsManager(models.Manager):
    def current(self) -> SiteSettings:
        """The single settings row, created on first use.

        A singleton rather than a settings file, because every value here
        is the agency's to change — and asking for a deploy to correct a
        phone number is how a phone number stays wrong.
        """
        obj = self.first()
        if obj is None:
            obj = self.create()
        return obj


class SiteSettings(TimeStampedModel):
    """One row. Brand and contact details for the whole site."""

    site_name = models.CharField(_("site name"), max_length=120, default="Heliograph")
    tagline = models.CharField(_("tagline"), max_length=200, blank=True)

    contact_email = models.EmailField(
        _("contact email"), max_length=254, blank=True,
        help_text=_("Shown on the site as a mailto link. The platform sends "
                    "nothing to it."),
    )
    contact_phone = models.CharField(_("phone"), max_length=32, blank=True)

    whatsapp_number = models.CharField(
        _("WhatsApp number"), max_length=32, blank=True,
        help_text=_("International format, digits only, e.g. 94771234567. "
                    "Used to build a wa.me link — the platform sends no "
                    "messages itself."),
    )
    whatsapp_message = models.CharField(
        _("WhatsApp prefilled message"), max_length=200, blank=True,
        help_text=_("Text the visitor's app opens with."),
    )

    address_line1 = models.CharField(_("address line 1"), max_length=200, blank=True)
    address_line2 = models.CharField(_("address line 2"), max_length=200, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=24, blank=True)
    country = models.CharField(_("country"), max_length=100, blank=True)

    # Defaults used by any page that does not set its own.
    default_meta_title = models.CharField(
        _("default page title"), max_length=70, blank=True,
        help_text=_("Up to about 60 characters before search engines truncate it."),
    )
    default_meta_description = models.CharField(
        _("default meta description"), max_length=180, blank=True,
        help_text=_("Up to about 155 characters."),
    )
    default_og_image = models.ImageField(
        _("default social share image"), upload_to="cms/social/", blank=True,
    )

    response_time_note = models.CharField(
        _("reply time note"), max_length=160, blank=True,
        help_text=_("Shown under enquiry and quote forms, for example "
                    "“We usually reply within one working day.” Left blank, "
                    "the site promises nothing — which is the safer default, "
                    "because a promise on the page is a promise to keep."),
    )

    footer_note = models.CharField(
        _("footer note"), max_length=200, blank=True,
        help_text=_("Shown beside the copyright line."),
    )

    objects = SiteSettingsManager()

    class Meta:
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")

    def __str__(self) -> str:
        return self.site_name

    def save(self, *args, **kwargs):
        """Collapse any save onto the one row.

        One row, always: a second would mean two answers to "what is the
        phone number". Setting the primary key is not enough on its own —
        Django decides between INSERT and UPDATE from `_state.adding`, and
        `objects.create()` additionally passes `force_insert=True`. Both
        have to be cleared, or this raises a duplicate key error instead
        of quietly updating — and the existing `created_at` has to be
        carried across, because `auto_now_add` fills it only on insert.
        """
        if not self.pk:
            existing = SiteSettings.objects.values("pk", "created_at").first()
            if existing is not None:
                self.pk = existing["pk"]
                # `auto_now_add` only fills on insert, so an update from a
                # fresh instance would write null over the real timestamp.
                self.created_at = existing["created_at"]
                self._state.adding = False
                kwargs.pop("force_insert", None)

        super().save(*args, **kwargs)

    @property
    def whatsapp_url(self) -> str:
        """A wa.me link, or empty if no number is set."""
        digits = "".join(character for character in self.whatsapp_number
                         if character.isdigit())
        if not digits:
            return ""

        url = f"https://wa.me/{digits}"
        if self.whatsapp_message:
            from urllib.parse import quote

            url = f"{url}?text={quote(self.whatsapp_message)}"
        return url

    @property
    def address_lines(self) -> list[str]:
        city_line = " ".join(filter(None, [self.city, self.postal_code])).strip()
        return [line for line in (self.address_line1, self.address_line2,
                                  city_line, self.country) if line]


# ---------------------------------------------------------------------------
# Shared collections
# ---------------------------------------------------------------------------


class OrderedVisibleQuerySet(models.QuerySet):
    """Shared by everything the admin orders and shows or hides."""

    def visible(self):
        return self.filter(is_visible=True)


class OrderedVisibleModel(TimeStampedModel):
    """Ordering and visibility, the two controls every collection needs."""

    order = models.PositiveIntegerField(
        _("order"), default=0, db_index=True,
        help_text=_("Lower numbers appear first."),
    )
    is_visible = models.BooleanField(
        _("visible"), default=True,
        help_text=_("Hidden entries stay in the admin but leave the public site."),
    )

    objects = OrderedVisibleQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["order", "pk"]


class SocialPlatform(models.TextChoices):
    LINKEDIN = "linkedin", "LinkedIn"
    INSTAGRAM = "instagram", "Instagram"
    FACEBOOK = "facebook", "Facebook"
    X = "x", "X"
    YOUTUBE = "youtube", "YouTube"
    TIKTOK = "tiktok", "TikTok"
    WHATSAPP = "whatsapp", "WhatsApp"


class SocialLink(OrderedVisibleModel):
    platform = models.CharField(_("platform"), max_length=20,
                                choices=SocialPlatform.choices)
    url = models.URLField(_("link"), max_length=300)
    label = models.CharField(
        _("accessible label"), max_length=60, blank=True,
        help_text=_("Overrides the default, e.g. “Heliograph on LinkedIn”."),
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("social link")
        verbose_name_plural = _("social links")

    def __str__(self) -> str:
        return self.get_platform_display()

    @property
    def accessible_label(self) -> str:
        return self.label or f"{self.get_platform_display()}"


class Testimonial(OrderedVisibleModel):
    quote = models.TextField(_("quote"))
    author_name = models.CharField(_("name"), max_length=120)
    author_role = models.CharField(_("role"), max_length=120, blank=True)
    company = models.CharField(_("company"), max_length=120, blank=True)
    photo = models.ImageField(_("photo"), upload_to="cms/testimonials/", blank=True)

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("testimonial")
        verbose_name_plural = _("testimonials")

    def __str__(self) -> str:
        return f"{self.author_name}{f' · {self.company}' if self.company else ''}"

    @property
    def attribution(self) -> str:
        return ", ".join(filter(None, [self.author_role, self.company]))


class TeamMember(OrderedVisibleModel):
    name = models.CharField(_("name"), max_length=120)
    role = models.CharField(_("role"), max_length=120, blank=True)
    bio = models.TextField(_("short bio"), blank=True)
    photo = models.ImageField(_("photo"), upload_to="cms/team/", blank=True)
    linkedin_url = models.URLField(_("LinkedIn"), max_length=300, blank=True)

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("team member")
        verbose_name_plural = _("team members")

    def __str__(self) -> str:
        return self.name


class FAQ(OrderedVisibleModel):
    question = models.CharField(_("question"), max_length=250)
    answer = models.TextField(_("answer"))
    category = models.CharField(
        _("group"), max_length=80, blank=True,
        help_text=_("Optional heading to group questions under."),
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("question and answer")
        verbose_name_plural = _("questions and answers")

    def __str__(self) -> str:
        return self.question


class BannerPlacement(models.TextChoices):
    SITE_TOP = "site_top", _("Top of every page")
    HOME_ONLY = "home_only", _("Home page only")


class PromoBanner(OrderedVisibleModel):
    """A short announcement strip.

    Carries its own dates so a campaign banner stops showing on time
    without anyone having to remember to take it down.
    """

    message = models.CharField(_("message"), max_length=200)
    cta_label = models.CharField(_("link text"), max_length=60, blank=True)
    cta_url = models.CharField(_("link"), max_length=300, blank=True)
    placement = models.CharField(_("placement"), max_length=20,
                                 choices=BannerPlacement.choices,
                                 default=BannerPlacement.SITE_TOP)
    tone = models.CharField(_("tone"), max_length=10, choices=Tone.choices,
                            default=Tone.NAVY)
    starts_at = models.DateTimeField(_("starts"), null=True, blank=True)
    ends_at = models.DateTimeField(_("ends"), null=True, blank=True)

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("promotional banner")
        verbose_name_plural = _("promotional banners")

    def __str__(self) -> str:
        return self.message

    def clean(self) -> None:
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": _("The end must come after the start.")})

    @property
    def is_live(self) -> bool:
        now = timezone.now()
        if not self.is_visible:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        return not (self.ends_at and self.ends_at <= now)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


class NavPlacement(models.TextChoices):
    HEADER = "header", _("Header")
    FOOTER_PRIMARY = "footer_primary", _("Footer — first column")
    FOOTER_SECONDARY = "footer_secondary", _("Footer — second column")
    LEGAL = "legal", _("Footer — legal")


class NavigationItem(OrderedVisibleModel):
    """One link in the header or footer.

    A link points either at a CMS page or at a URL, never both — two
    destinations would make the resolved link depend on which field the
    template happened to read.
    """

    label = models.CharField(_("label"), max_length=60)
    placement = models.CharField(_("placement"), max_length=20,
                                 choices=NavPlacement.choices,
                                 default=NavPlacement.HEADER, db_index=True)
    page = models.ForeignKey(
        "cms.Page", on_delete=models.CASCADE, null=True, blank=True,
        related_name="navigation_items", verbose_name=_("page"),
    )
    url = models.CharField(
        _("or a link"), max_length=300, blank=True,
        help_text=_("An internal path like /services/ or a full external URL."),
    )
    opens_in_new_tab = models.BooleanField(_("open in a new tab"), default=False)
    is_cta = models.BooleanField(
        _("show as a button"), default=False,
        help_text=_("Header only. Use for the one action that matters most."),
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("navigation item")
        verbose_name_plural = _("navigation items")
        indexes = [
            models.Index(fields=["placement", "order"], name="nav_placement_order_idx"),
        ]

    def __str__(self) -> str:
        return self.label

    def clean(self) -> None:
        if self.page_id and self.url:
            raise ValidationError(
                _("Choose a page or enter a link, not both.")
            )
        if not self.page_id and not self.url:
            raise ValidationError(
                _("A navigation item needs somewhere to go.")
            )

    @property
    def href(self) -> str:
        if self.page_id:
            return self.page.get_absolute_url()
        return self.url


class WebsiteCopy(TimeStampedModel):
    """Plain-text overrides for public template copy outside CMS page sections."""
    key = models.CharField(max_length=200, unique=True)
    text = models.TextField(max_length=10000, blank=True)

    class Meta:
        ordering = ['key']
