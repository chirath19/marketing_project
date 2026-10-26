"""Write operations for the service catalogue."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.text import slugify

from apps.catalog import policies
from apps.catalog.models import PackageFeature, Service, ServicePackage
from apps.core.events import DomainEvent, bus

logger = logging.getLogger(__name__)


def _unique_slug(model, value: str, *, exclude_pk: int | None = None,
                 scope: dict | None = None) -> str:
    base = slugify(value)[:150] or "item"
    queryset = model.objects.exclude(pk=exclude_pk)
    if scope:
        queryset = queryset.filter(**scope)

    taken = set(queryset.filter(slug__startswith=base).values_list("slug", flat=True))

    candidate = base
    suffix = 2
    while candidate in taken:
        candidate = f"{base}-{suffix}"[:170]
        suffix += 1
    return candidate


@transaction.atomic
def save_catalog_object(*, form, actor, created: bool = False):  # noqa: ANN001, ANN201
    """Persist a catalogue form.

    Creating and editing need different rights, so which one is required
    depends on whether the row is new.
    """
    allowed = (policies.can_create_catalog(actor) if created
               else policies.can_edit_catalog(actor))
    if not allowed:
        raise PermissionDenied("You may not change the service catalogue.")

    instance = form.save(commit=False)

    if hasattr(instance, "slug") and not instance.slug:
        name = getattr(instance, "name", "") or ""
        scope = ({"service_id": instance.service_id}
                 if isinstance(instance, ServicePackage) else None)
        instance.slug = _unique_slug(type(instance), name,
                                     exclude_pk=instance.pk, scope=scope)

    if created and hasattr(instance, "order") and not instance.order:
        siblings = type(instance).objects.all()
        for scope_field in ("service_id", "category_id"):
            if getattr(instance, scope_field, None):
                siblings = siblings.filter(**{scope_field: getattr(instance, scope_field)})
        instance.order = (siblings.aggregate(top=Max("order"))["top"] or 0) + 10

    instance.full_clean()
    instance.save()
    if hasattr(form, "save_m2m"):
        form.save_m2m()

    bus.publish(DomainEvent("catalog.saved", {
        "model": type(instance).__name__, "pk": instance.pk,
        "created": created, "actor_id": getattr(actor, "pk", None),
    }))
    return instance


@transaction.atomic
def delete_catalog_object(*, instance, actor) -> None:  # noqa: ANN001
    if not policies.can_delete_catalog(actor):
        raise PermissionDenied("You may not delete catalogue entries.")

    label = str(instance)
    model = type(instance).__name__
    instance.delete()

    bus.publish(DomainEvent("catalog.deleted", {
        "model": model, "label": label, "actor_id": getattr(actor, "pk", None),
    }))


@transaction.atomic
def set_service_visibility(*, service: Service, actor, visible: bool) -> Service:
    """Show or hide a service on the public catalogue.

    Publishing rather than editing: this is the decision that puts a
    price in front of the public.
    """
    if not policies.can_publish_catalog(actor):
        raise PermissionDenied("You may not publish catalogue entries.")

    service.is_visible = visible
    service.save(update_fields=["is_visible", "updated_at"])

    bus.publish(DomainEvent("catalog.service_visibility_changed", {
        "service_id": service.pk, "visible": visible,
        "actor_id": getattr(actor, "pk", None),
    }))
    logger.info("Service %s %s", service.slug, "shown" if visible else "hidden")
    return service


@transaction.atomic
def set_service_active(*, service: Service, actor, active: bool) -> Service:
    """Retire a service, or bring it back.

    Separate from visibility: retiring means the agency no longer sells
    it, which is a commercial decision, while hiding is an editorial one.
    The row is kept either way, because quotes and subscriptions
    reference it.
    """
    if not policies.can_publish_catalog(actor):
        raise PermissionDenied("You may not retire catalogue entries.")

    service.is_active = active
    service.save(update_fields=["is_active", "updated_at"])

    bus.publish(DomainEvent("catalog.service_active_changed", {
        "service_id": service.pk, "active": active,
        "actor_id": getattr(actor, "pk", None),
    }))
    return service


@transaction.atomic
def move(*, instance, actor, direction: str):  # noqa: ANN001, ANN201
    """Swap a row with its neighbour within its own scope."""
    if not policies.can_edit_catalog(actor):
        raise PermissionDenied("You may not change the service catalogue.")

    if direction not in {"up", "down"}:
        raise ValidationError("Direction must be 'up' or 'down'.")

    siblings = type(instance).objects.all()
    for scope in ("service_id", "category_id"):
        if getattr(instance, scope, None):
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
def set_package_features(*, package: ServicePackage, actor,
                         included_ids: list[int]) -> ServicePackage:
    """Replace which of the service's features this package includes.

    Replace rather than merge, so unticking a box in the editor actually
    removes the feature.
    """
    if not policies.can_edit_catalog(actor):
        raise PermissionDenied("You may not change the service catalogue.")

    valid_ids = set(
        package.service.features.filter(pk__in=included_ids).values_list("pk", flat=True)
    )

    PackageFeature.objects.filter(package=package).exclude(
        feature_id__in=valid_ids
    ).delete()

    existing = set(
        PackageFeature.objects.filter(package=package)
        .values_list("feature_id", flat=True)
    )
    PackageFeature.objects.bulk_create([
        PackageFeature(package=package, feature_id=feature_id, is_included=True)
        for feature_id in valid_ids - existing
    ])

    return package
