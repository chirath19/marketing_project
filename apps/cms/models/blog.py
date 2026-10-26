"""The blog.

Posts are stored as plain text and rendered by `apps.cms.richtext`, which
escapes first and then produces a fixed set of elements. Storing HTML
would mean trusting whatever is pasted into the field, or running a
sanitiser over it on every read.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.cms.models.site import OrderedVisibleModel, PublishStatus
from apps.core.models import TimeStampedModel


class Category(OrderedVisibleModel):
    """One category per post. A post belongs somewhere, or nowhere."""

    name = models.CharField(_("name"), max_length=80, unique=True)
    slug = models.SlugField(_("slug"), max_length=90, unique=True)
    description = models.CharField(
        _("description"), max_length=250, blank=True,
        help_text=_("Shown at the top of the category's own page, and used "
                    "as its meta description."),
    )

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("public:blog_category", kwargs={"slug": self.slug})


class Tag(OrderedVisibleModel):
    """A cross-cutting label. A post can carry several."""

    name = models.CharField(_("name"), max_length=60, unique=True)
    slug = models.SlugField(_("slug"), max_length=70, unique=True)

    class Meta(OrderedVisibleModel.Meta):
        verbose_name = _("tag")
        verbose_name_plural = _("tags")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("public:blog_tag", kwargs={"slug": self.slug})


class BlogPostQuerySet(models.QuerySet):
    def published(self):
        """Live posts only.

        A future `published_at` keeps a post off the site until its date,
        so a post can be written on Monday and scheduled for Thursday
        without anyone having to remember to press publish.
        """
        return self.filter(status=PublishStatus.PUBLISHED,
                           published_at__lte=timezone.now())

    def for_listing(self):
        return (
            self.select_related("category", "author")
            .prefetch_related("tags")
            .order_by("-published_at", "-pk")
        )


class BlogPost(TimeStampedModel):
    title = models.CharField(_("title"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220, unique=True,
                            help_text=_("The address. Changing it breaks "
                                        "existing links and shares."))

    excerpt = models.CharField(
        _("excerpt"), max_length=300, blank=True,
        help_text=_("One or two sentences for the listing and for search "
                    "results. Falls back to the opening of the post."),
    )
    content = models.TextField(
        _("content"),
        help_text=_("Plain text. Blank lines separate paragraphs. "
                    "## heading, - list, > quote, **bold**, [text](link)."),
    )

    featured_image = models.ImageField(_("featured image"),
                                       upload_to="blog/", blank=True)
    featured_image_alt = models.CharField(
        _("image description"), max_length=200, blank=True,
        help_text=_("What the image shows, for people who cannot see it."),
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="blog_posts", verbose_name=_("author"),
        help_text=_("Kept if the account is later closed, so the post keeps "
                    "its byline."),
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="posts", verbose_name=_("category"),
    )
    tags = models.ManyToManyField(Tag, related_name="posts", blank=True,
                                  verbose_name=_("tags"))

    status = models.CharField(_("status"), max_length=20,
                              choices=PublishStatus.choices,
                              default=PublishStatus.DRAFT, db_index=True)
    published_at = models.DateTimeField(
        _("publication date"), null=True, blank=True,
        help_text=_("A future date holds the post back until then."),
    )

    meta_title = models.CharField(
        _("search engine title"), max_length=70, blank=True,
        help_text=_("Defaults to the title. About 60 characters."),
    )
    meta_description = models.CharField(
        _("meta description"), max_length=180, blank=True,
        help_text=_("Defaults to the excerpt. About 155 characters."),
    )

    objects = BlogPostQuerySet.as_manager()

    class Meta:
        verbose_name = _("blog post")
        verbose_name_plural = _("blog posts")
        ordering = ["-published_at", "-pk"]
        indexes = [
            # The listing query: live posts, newest first.
            models.Index(fields=["status", "-published_at"],
                         name="post_status_published_idx"),
            models.Index(fields=["category", "status"],
                         name="post_category_status_idx"),
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        if self.featured_image and not self.featured_image_alt:
            raise ValidationError({
                "featured_image_alt": _(
                    "Describe the image, or remove it. An image with no "
                    "description is invisible to anyone using a screen reader."
                ),
            })

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("public:blog_detail", kwargs={"slug": self.slug})

    # --- derived -----------------------------------------------------------

    @property
    def is_published(self) -> bool:
        return (self.status == PublishStatus.PUBLISHED
                and self.published_at is not None
                and self.published_at <= timezone.now())

    @property
    def is_scheduled(self) -> bool:
        """Published, but dated in the future."""
        return (self.status == PublishStatus.PUBLISHED
                and self.published_at is not None
                and self.published_at > timezone.now())

    @property
    def body_html(self) -> str:
        from apps.cms.richtext import render

        return render(self.content)

    @property
    def summary(self) -> str:
        """The excerpt, or the opening of the post if none was written."""
        if self.excerpt:
            return self.excerpt

        from apps.cms.richtext import plain_text

        text = plain_text(self.content)
        return f"{text[:197]}…" if len(text) > 200 else text

    @property
    def reading_minutes(self) -> int:
        from apps.cms.richtext import reading_minutes

        return reading_minutes(self.content)

    @property
    def byline(self) -> str:
        """The author's name, or nothing.

        Deliberately not `get_full_name()`: that falls back to the email
        address, which would publish a staff member's email on the public
        site. A post with no name on the account simply has no byline.
        """
        return self.author.full_name.strip() if self.author else ""

    def resolved_meta_title(self) -> str:
        return self.meta_title or self.title

    def resolved_meta_description(self) -> str:
        return self.meta_description or self.summary
