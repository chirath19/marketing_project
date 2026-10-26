"""The service catalogue.

Everything a visitor sees on the services pages lives here. Nothing is
hard-coded: a new service, a price change, a reordered category or a
retired package is an editing task.

Three levels, each optional below the first:

* **Service** — what the agency sells. Carries a headline price.
* **ServicePackage** — tiers of one service, where it has them. A service
  with no packages simply shows its own price.
* **ServiceFeature** — the "what is included" list. Packages mark which
  features they include, which is what makes a comparison table possible
  without retyping the list per tier.

`ServiceAddon` hangs off a service, or off nothing in particular when it
is something any client can bolt on.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.cms.models import OrderedVisibleModel
from apps.core.modules import MODULE_CHOICES


class BillingType(models.TextChoices):
    """How a price is charged.

    `CUSTOM` carries no number: some work genuinely cannot be priced
    until it has been scoped, and inventing a figure for the sake of
    filling the field would be worse than saying so.
    """

    ONE_TIME = "one_time", _("One time")
    MONTHLY = "monthly", _("Per month")
    CUSTOM = "custom", _("Custom quote")


#: Billing types that must carry a price. `CUSTOM` must not.
PRICED_BILLING_TYPES = frozenset({BillingType.ONE_TIME, BillingType.MONTHLY})


class PriceMixin(models.Model):
    """A price and how it is charged.

    Stored as a decimal, never a float: money that drifts by a hundredth
    of a cent is money that eventually disagrees with an invoice.
    """

    price_visibility = models.CharField(
        max_length=10,
        default="inherit",
        choices=[
            ("inherit", "Use site default"),
            ("show", "Show publicly"),
            ("hide", "Hide publicly"),
        ],
        help_text="Controls public pricing only; agreed proposals remain visible to their client.",
    )

    price = models.DecimalField(
        _("price"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Leave empty for a custom quote."),
    )
    currency = models.CharField(
        _("currency"),
        max_length=3,
        default="USD",
        help_text=_("Three-letter code, e.g. USD."),
    )
    billing_type = models.CharField(
        _("billing"),
        max_length=20,
        choices=BillingType.choices,
        default=BillingType.MONTHLY,
    )

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()

        if self.billing_type in PRICED_BILLING_TYPES and self.price is None:
            raise ValidationError(
                {
                    "price": _(
                        "A %(billing)s price needs a number. Choose "
                        "“Custom quote” if it cannot be priced yet."
                    )
                    % {"billing": self.get_billing_type_display().lower()},
                }
            )

        if self.billing_type == BillingType.CUSTOM and self.price is not None:
            raise ValidationError(
                {
                    "price": _(
                        "A custom quote has no fixed price. Clear the "
                        "price, or choose a different billing type."
                    ),
                }
            )

    @property
    def is_custom_priced(self) -> bool:
        return self.billing_type == BillingType.CUSTOM

    @property
    def price_display(self) -> str:
        """The headline figure, as the catalogue shows it.

        Whole amounts lose their decimals: "$2,400" reads as a price,
        "$2,400.00" reads as an invoice line.
        """
        if self.price is None:
            return str(_("Custom quote"))

        symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(self.currency, "")
        whole = self.price == self.price.to_integral_value()
        amount = self.price.quantize(Decimal("1")) if whole else self.price
        formatted = f"{amount:,}"
        return f"{symbol}{formatted}" if symbol else f"{formatted} {self.currency}"

    @property
    def billing_display(self) -> str:
        """The words under the price. Empty for a custom quote, which
        already says so in the figure."""
        if self.billing_type == BillingType.CUSTOM:
            return ""
        return str(self.get_billing_type_display()).lower()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


def _lines(value: str) -> list[str]:
    """Split an editor's line-per-item field into items.

    Blank lines and stray whitespace are dropped rather than rendered as
    empty bullets: an editor should not have to be tidy for the page to
    look deliberate.
    """
    return [line.strip() for line in value.splitlines() if line.strip()]


class ServiceCategory(OrderedVisibleModel):
    """A grouping on the catalogue page — Search, Paid, Social, Email."""

    name = models.CharField(_("name"), max_length=80, unique=True)
    slug = models.SlugField(_("slug"), max_length=90, unique=True)
    short_description = models.CharField(
        _("short description"),
        max_length=250,
        blank=True,
        help_text=_("Shown under the heading on the category's own view."),
    )
    icon = models.CharField(
        _("icon"),
        max_length=8,
        blank=True,
        help_text=_("A single character or emoji. Decorative only."),
    )
    workspace_module = models.CharField(
        _("unlocks in the client workspace"),
        max_length=30,
        blank=True,
        choices=MODULE_CHOICES,
        help_text=_(
            "The area a client gains access to while they have an "
            "active service in this category. Leave blank for a "
            "category that is sold without a dashboard behind it."
        ),
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("service category")
        verbose_name_plural = _("service categories")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("public:services_category", kwargs={"slug": self.slug})


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


class ServiceQuerySet(models.QuerySet):
    def live(self):
        """What the public may see.

        Two switches, because they mean different things: `is_active` is
        whether the agency still sells it, `is_visible` is whether it is
        on the page. A service can be quietly retired without vanishing
        from the quotes that already reference it.
        """
        return self.filter(is_active=True, is_visible=True)

    def for_listing(self):
        return (
            self.select_related("category")
            .prefetch_related("features", "packages")
            .order_by("order", "name")
        )


class Service(PriceMixin, OrderedVisibleModel):
    name = models.CharField(_("name"), max_length=150)
    slug = models.SlugField(_("slug"), max_length=170, unique=True)
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="services",
        verbose_name=_("category"),
    )

    short_description = models.CharField(
        _("short description"),
        max_length=300,
        help_text=_("One or two sentences. Shown on the catalogue card."),
    )
    full_description = models.TextField(
        _("full description"),
        blank=True,
        help_text=_(
            "Shown on the service's own page. Blank lines separate "
            "paragraphs; the same formatting as a blog post."
        ),
    )

    ideal_for = models.TextField(
        _("who this is for"),
        blank=True,
        help_text=_(
            "One line per kind of business this suits. A visitor "
            "who cannot tell whether a service is meant for them "
            "does not enquire."
        ),
    )
    deliverables = models.TextField(
        _("what you receive"),
        blank=True,
        help_text=_(
            "One line per thing the client actually gets. Distinct "
            "from the feature list: these are the artefacts, not "
            "the activities."
        ),
    )
    process = models.TextField(
        _("how it runs"),
        blank=True,
        help_text=_(
            "One step per line, in order. Written for this service "
            "specifically — the same six generic steps on every "
            "page tell a buyer nothing."
        ),
    )
    reporting = models.CharField(
        _("how it is reported"),
        max_length=300,
        blank=True,
        help_text=_("What the client sees, and how often."),
    )

    image = models.ImageField(_("image"), upload_to="catalog/", blank=True)
    image_alt = models.CharField(_("image description"), max_length=200, blank=True)
    icon = models.CharField(
        _("icon"),
        max_length=8,
        blank=True,
        help_text=_("A single character or emoji. Decorative only."),
    )

    is_active = models.BooleanField(
        _("still sold"),
        default=True,
        help_text=_(
            "Turn off to retire a service. It leaves the catalogue "
            "but stays attached to anything that already references it."
        ),
    )
    is_featured = models.BooleanField(
        _("featured"),
        default=False,
        help_text=_("Highlighted at the top of the catalogue."),
    )
    can_request_quote = models.BooleanField(
        _("available for quotes"),
        default=True,
        help_text=_(
            "Lets a visitor add this to a quote request. Turn off "
            "for something only sold as part of something else."
        ),
    )

    meta_title = models.CharField(_("search engine title"), max_length=70, blank=True)
    meta_description = models.CharField(_("meta description"), max_length=180, blank=True)

    objects = ServiceQuerySet.as_manager()

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("service")
        verbose_name_plural = _("services")
        indexes = [
            models.Index(
                fields=["is_active", "is_visible", "order"], name="service_live_order_idx"
            ),
            models.Index(fields=["category", "order"], name="service_cat_order_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("public:service_detail", kwargs={"slug": self.slug})

    def clean(self) -> None:
        super().clean()
        if self.image and not self.image_alt:
            raise ValidationError(
                {
                    "image_alt": _("Describe the image, or remove it."),
                }
            )

    # --- derived -----------------------------------------------------------

    @property
    def is_live(self) -> bool:
        return self.is_active and self.is_visible

    @property
    def paragraphs(self) -> list[str]:
        return [block.strip() for block in self.full_description.split("\n\n") if block.strip()]

    @property
    def ideal_for_lines(self) -> list[str]:
        return _lines(self.ideal_for)

    @property
    def deliverable_lines(self) -> list[str]:
        return _lines(self.deliverables)

    @property
    def process_steps(self) -> list[str]:
        return _lines(self.process)

    @property
    def has_packages(self) -> bool:
        return self.packages.exists()

    def resolved_meta_title(self) -> str:
        return self.meta_title or self.name

    def resolved_meta_description(self) -> str:
        return self.meta_description or self.short_description


class ServiceFeature(OrderedVisibleModel):
    """One line of a service's "what is included" list.

    Owned by the service rather than by a package, so a comparison table
    can show the same row across every tier without the list being
    retyped for each one.
    """

    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="features", verbose_name=_("service")
    )
    label = models.CharField(_("feature"), max_length=160)
    description = models.CharField(_("detail"), max_length=250, blank=True)

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("service feature")
        verbose_name_plural = _("service features")
        indexes = [
            models.Index(fields=["service", "order"], name="feature_service_idx"),
        ]

    def __str__(self) -> str:
        return self.label


class ServicePackage(PriceMixin, OrderedVisibleModel):
    """A tier of a service. A service without tiers has none of these."""

    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="packages", verbose_name=_("service")
    )
    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("slug"), max_length=140)
    summary = models.CharField(
        _("summary"), max_length=250, blank=True, help_text=_("Who this tier is for.")
    )

    is_recommended = models.BooleanField(
        _("recommended"),
        default=False,
        help_text=_("Marked as the suggested choice in the comparison."),
    )

    features = models.ManyToManyField(
        ServiceFeature,
        through="PackageFeature",
        related_name="packages",
        blank=True,
        verbose_name=_("features"),
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("service package")
        verbose_name_plural = _("service packages")
        constraints = [
            models.UniqueConstraint(
                fields=["service", "slug"], name="unique_package_slug_per_service"
            ),
        ]
        indexes = [
            models.Index(fields=["service", "order"], name="package_service_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.service.name} — {self.name}"

    def includes(self, feature: ServiceFeature) -> bool:
        return self.package_features.filter(feature=feature, is_included=True).exists()


class PackageFeature(models.Model):
    """Whether one package includes one feature, and to what extent.

    `value` carries a quantity where a yes/no is not enough — "2 channels"
    against "4 channels" — which is what makes a comparison table useful
    rather than a grid of ticks.
    """

    package = models.ForeignKey(
        ServicePackage, on_delete=models.CASCADE, related_name="package_features"
    )
    feature = models.ForeignKey(
        ServiceFeature, on_delete=models.CASCADE, related_name="package_links"
    )
    is_included = models.BooleanField(_("included"), default=True)
    value = models.CharField(
        _("detail"),
        max_length=80,
        blank=True,
        help_text=_("Shown instead of a tick, e.g. “4 channels”."),
    )

    class Meta:
        verbose_name = _("package feature")
        verbose_name_plural = _("package features")
        constraints = [
            models.UniqueConstraint(
                fields=["package", "feature"], name="unique_feature_per_package"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.package} · {self.feature}"

    def clean(self) -> None:
        if (
            self.package_id
            and self.feature_id
            and (self.package.service_id != self.feature.service_id)
        ):
            raise ValidationError(_("A package can only include features from its own service."))


class ServiceAddon(PriceMixin, OrderedVisibleModel):
    """Something bolted on to a service, or sold alongside any of them."""

    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="addons",
        null=True,
        blank=True,
        verbose_name=_("service"),
        help_text=_("Leave empty for an add-on that applies to anything."),
    )
    name = models.CharField(_("name"), max_length=150)
    slug = models.SlugField(_("slug"), max_length=170, unique=True)
    short_description = models.CharField(_("short description"), max_length=300, blank=True)
    is_active = models.BooleanField(_("still sold"), default=True)

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("service add-on")
        verbose_name_plural = _("service add-ons")

    def __str__(self) -> str:
        return self.name

    @property
    def is_live(self) -> bool:
        return self.is_active and self.is_visible


class ServiceFaq(OrderedVisibleModel):
    """A question asked about one service.

    Deliberately here and not in the shared CMS FAQ collection: that one
    answers questions about the agency, and it must not grow a foreign
    key into the catalogue. A question about what a Google Ads retainer
    covers belongs to the thing it is about.
    """

    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="faqs", verbose_name=_("service")
    )
    question = models.CharField(_("question"), max_length=200)
    answer = models.TextField(_("answer"))

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("service question")
        verbose_name_plural = _("service questions")

    def __str__(self) -> str:
        return self.question
