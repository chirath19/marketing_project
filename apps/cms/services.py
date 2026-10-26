"""Write operations for the CMS."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify

from apps.cms import policies
from apps.cms.models import Page, PageKind, PublishStatus, SiteSettings
from apps.core.events import DomainEvent, bus

logger = logging.getLogger(__name__)


def _unique_slug(value: str, *, exclude_pk: int | None = None) -> str:
    base = slugify(value)[:150] or "page"
    taken = set(
        Page.objects.exclude(pk=exclude_pk).filter(slug__startswith=base)
        .values_list("slug", flat=True)
    )

    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"[:160]
        suffix += 1
    return candidate


@transaction.atomic
def create_page(*, title: str, actor, kind: str = PageKind.STANDARD,
                slug: str = "", **fields) -> Page:
    if not policies.can_create_content(actor):
        raise PermissionDenied("You may not create pages.")

    cleaned = (title or "").strip()
    if not cleaned:
        raise ValidationError("A page needs a title.")

    if kind != PageKind.STANDARD and Page.objects.filter(kind=kind).exists():
        raise ValidationError(
            f"There is already a {kind} page. A site has one of each."
        )

    page = Page.objects.create(
        title=cleaned,
        slug=_unique_slug(slug or cleaned),
        kind=kind,
        **fields,
    )

    bus.publish(DomainEvent("cms.page_created", {
        "page_id": page.pk, "slug": page.slug,
        "actor_id": getattr(actor, "pk", None),
    }))
    return page


@transaction.atomic
def publish_page(*, page: Page, actor) -> Page:
    """Put a page in front of the public.

    A separate right from editing: preparing a page and deciding it is
    ready are different decisions, often made by different people.
    """
    if not policies.can_publish(actor):
        raise PermissionDenied("You may not publish pages.")

    page.status = PublishStatus.PUBLISHED
    page.published_at = page.published_at or timezone.now()
    page.save(update_fields=["status", "published_at", "updated_at"])

    bus.publish(DomainEvent("cms.page_published", {
        "page_id": page.pk, "slug": page.slug,
        "actor_id": getattr(actor, "pk", None),
    }))
    logger.info("Page published: %s", page.slug)
    return page


@transaction.atomic
def unpublish_page(*, page: Page, actor) -> Page:
    if not policies.can_publish(actor):
        raise PermissionDenied("You may not unpublish pages.")

    page.status = PublishStatus.DRAFT
    page.save(update_fields=["status", "updated_at"])

    bus.publish(DomainEvent("cms.page_unpublished", {
        "page_id": page.pk, "slug": page.slug,
        "actor_id": getattr(actor, "pk", None),
    }))
    return page


@transaction.atomic
def save_object(*, form, actor, created: bool = False):  # noqa: ANN001, ANN201
    """Persist a CMS form, with the right permission for the operation.

    Creating and editing are different rights, so which one is required
    depends on whether the row is new.
    """
    allowed = (policies.can_create_content(actor) if created
               else policies.can_edit_content(actor))
    if not allowed:
        raise PermissionDenied("You may not change website content.")

    instance = form.save(commit=False)

    # New ordered rows go to the end rather than colliding on 0.
    if created and hasattr(instance, "order") and not instance.order:
        siblings = type(instance).objects.all()
        if hasattr(instance, "page_id") and instance.page_id:
            siblings = siblings.filter(page_id=instance.page_id)
        if hasattr(instance, "section_id") and instance.section_id:
            siblings = siblings.filter(section_id=instance.section_id)
        instance.order = (siblings.aggregate(top=Max("order"))["top"] or 0) + 10

    instance.full_clean()
    instance.save()
    form.save_m2m() if hasattr(form, "save_m2m") else None

    bus.publish(DomainEvent("cms.content_saved", {
        "model": type(instance).__name__, "pk": instance.pk,
        "created": created, "actor_id": getattr(actor, "pk", None),
    }))
    return instance


@transaction.atomic
def delete_object(*, instance, actor) -> None:  # noqa: ANN001
    if not policies.can_delete_content(actor):
        raise PermissionDenied("You may not delete website content.")

    label = str(instance)
    model = type(instance).__name__
    instance.delete()

    bus.publish(DomainEvent("cms.content_deleted", {
        "model": model, "label": label, "actor_id": getattr(actor, "pk", None),
    }))


@transaction.atomic
def set_visibility(*, instance, actor, visible: bool):  # noqa: ANN001, ANN201
    if not policies.can_edit_content(actor):
        raise PermissionDenied("You may not change website content.")

    instance.is_visible = visible
    instance.save(update_fields=["is_visible", "updated_at"])
    return instance


@transaction.atomic
def move(*, instance, actor, direction: str):  # noqa: ANN001, ANN201
    """Swap a row with its neighbour.

    Swapping two `order` values rather than renumbering the whole list
    keeps the operation to two writes and cannot leave the list in a
    half-renumbered state if something fails.
    """
    if not policies.can_edit_content(actor):
        raise PermissionDenied("You may not change website content.")

    if direction not in {"up", "down"}:
        raise ValidationError("Direction must be 'up' or 'down'.")

    siblings = type(instance).objects.all()
    for scope in ("page_id", "section_id", "placement"):
        if hasattr(instance, scope) and getattr(instance, scope) is not None:
            siblings = siblings.filter(**{scope: getattr(instance, scope)})

    if direction == "up":
        neighbour = (siblings.filter(order__lt=instance.order)
                     .order_by("-order", "-pk").first())
    else:
        neighbour = (siblings.filter(order__gt=instance.order)
                     .order_by("order", "pk").first())

    if neighbour is None:
        return instance

    instance.order, neighbour.order = neighbour.order, instance.order
    instance.save(update_fields=["order", "updated_at"])
    neighbour.save(update_fields=["order", "updated_at"])
    return instance


@transaction.atomic
def update_site_settings(*, form, actor) -> SiteSettings:
    if not policies.can_edit_content(actor):
        raise PermissionDenied("You may not change website content.")

    settings_row = form.save(commit=False)
    settings_row.full_clean()
    settings_row.save()

    bus.publish(DomainEvent("cms.site_settings_updated", {
        "actor_id": getattr(actor, "pk", None),
    }))
    return settings_row


# ---------------------------------------------------------------------------
# Blog
# ---------------------------------------------------------------------------


def _unique_post_slug(value: str, *, exclude_pk: int | None = None) -> str:
    from apps.cms.models import BlogPost

    base = slugify(value)[:200] or "post"
    taken = set(
        BlogPost.objects.exclude(pk=exclude_pk).filter(slug__startswith=base)
        .values_list("slug", flat=True)
    )

    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"[:220]
        suffix += 1
    return candidate


@transaction.atomic
def save_post(*, form, actor, created: bool = False):  # noqa: ANN001, ANN201
    """Create or update a post.

    The author is set once, on creation, and never overwritten: a
    colleague fixing a typo should not take the byline.
    """
    allowed = (policies.can_create_blog(actor) if created
               else policies.can_edit_blog(actor))
    if not allowed:
        raise PermissionDenied("You may not change blog posts.")

    post = form.save(commit=False)

    if not post.slug:
        post.slug = _unique_post_slug(post.title, exclude_pk=post.pk)

    if created and post.author_id is None:
        post.author = actor if getattr(actor, "pk", None) else None

    post.full_clean(exclude=["author"])
    post.save()
    form.save_m2m()

    bus.publish(DomainEvent("blog.post_saved", {
        "post_id": post.pk, "slug": post.slug, "created": created,
        "actor_id": getattr(actor, "pk", None),
    }))
    return post


@transaction.atomic
def publish_post(*, post, actor):  # noqa: ANN001, ANN201
    """Put a post live.

    The publication date is set on first publish and kept afterwards, so
    unpublishing to fix a typo and republishing does not move the post to
    the top of the listing.
    """
    if not policies.can_publish_blog(actor):
        raise PermissionDenied("You may not publish posts.")

    post.status = PublishStatus.PUBLISHED
    post.published_at = post.published_at or timezone.now()
    post.save(update_fields=["status", "published_at", "updated_at"])

    bus.publish(DomainEvent("blog.post_published", {
        "post_id": post.pk, "slug": post.slug,
        "actor_id": getattr(actor, "pk", None),
    }))
    logger.info("Post published: %s", post.slug)
    return post


@transaction.atomic
def delete_post(*, post, actor) -> None:  # noqa: ANN001
    """Remove a post.

    Its own permission rather than the CMS-wide one: deleting a published
    article is a different decision from tidying a page section, and often
    a different person's.
    """
    from apps.permissions.access import has_permission
    from apps.permissions.catalogue import permission_string

    allowed = (getattr(actor, "is_super_admin", False)
               or has_permission(actor, permission_string("blog", "delete")))
    if not allowed:
        raise PermissionDenied("You may not delete posts.")

    slug = post.slug
    post.delete()

    bus.publish(DomainEvent("blog.post_deleted", {
        "slug": slug, "actor_id": getattr(actor, "pk", None),
    }))


@transaction.atomic
def unpublish_post(*, post, actor):  # noqa: ANN001, ANN201
    if not policies.can_publish_blog(actor):
        raise PermissionDenied("You may not unpublish posts.")

    post.status = PublishStatus.DRAFT
    post.save(update_fields=["status", "updated_at"])

    bus.publish(DomainEvent("blog.post_unpublished", {
        "post_id": post.pk, "slug": post.slug,
        "actor_id": getattr(actor, "pk", None),
    }))
    return post
