"""Read access for the service catalogue.

Public reads go through `live_*`, which applies both switches —
`is_active` (still sold) and `is_visible` (on the page). Staff reads see
everything, because an editor has to be able to find the thing they
retired.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, Q, QuerySet

from apps.catalog.models import (
    PackageFeature,
    Service,
    ServiceAddon,
    ServiceCategory,
    ServiceFeature,
    ServicePackage,
)


def live_services() -> QuerySet:
    """Services the public may see, ready to list.

    The features and packages a card needs are prefetched, so a page of
    twelve services is a handful of queries rather than fifty.
    """
    return (
        Service.objects.live()
        .select_related("category")
        .prefetch_related(
            Prefetch("features",
                     queryset=ServiceFeature.objects.visible().order_by("order", "pk")),
            Prefetch("packages",
                     queryset=ServicePackage.objects.visible().order_by("order", "pk")),
        )
        .order_by("order", "name")
    )


def featured_services() -> QuerySet:
    return live_services().filter(is_featured=True)


def services_in_category(slug: str) -> QuerySet:
    return live_services().filter(category__slug=slug)


def related_services(service, limit: int = 3) -> QuerySet:
    """Other services somebody looking at this one might also need.

    Same category first, because that is the nearest thing to a real
    relationship the catalogue models. Deliberately not a hand-curated
    list: one more thing for an editor to keep in step with a catalogue
    that changes, and it would be wrong within a month.
    """
    return (
        live_services()
        .filter(category=service.category)
        .exclude(pk=service.pk)
        .order_by("order", "pk")[:limit]
    )


def live_service(slug: str):  # noqa: ANN201
    """One service, with everything its detail page shows."""
    return (
        live_services()
        .prefetch_related(
            Prefetch("addons",
                     queryset=ServiceAddon.objects.filter(is_active=True)
                     .visible().order_by("order", "pk")),
        )
        .filter(slug=slug)
        .first()
    )


def live_categories() -> QuerySet:
    """Categories with at least one live service.

    An empty category is a filter that leads nowhere, so it is not
    offered.
    """
    return (
        ServiceCategory.objects.visible()
        .annotate(service_count=Count(
            "services",
            filter=Q(services__is_active=True, services__is_visible=True),
            distinct=True,
        ))
        .filter(service_count__gt=0)
        .order_by("order", "name")
    )


def comparison_for(service: Service) -> dict | None:
    """The data a package comparison table needs, or None.

    Returns the packages as columns and the service's features as rows,
    with each cell already resolved to a tick, a value or a blank. Doing
    it here rather than in the template keeps the lookup to one query
    instead of one per cell.
    """
    packages = list(service.packages.visible().order_by("order", "pk"))
    if len(packages) < 2:
        # One tier is not a comparison; the service's own price says it.
        return None

    features = list(service.features.visible().order_by("order", "pk"))
    if not features:
        return None

    links = {
        (link.package_id, link.feature_id): link
        for link in PackageFeature.objects.filter(package__in=packages)
    }

    rows = []
    for feature in features:
        cells = []
        for package in packages:
            link = links.get((package.pk, feature.pk))
            cells.append({
                "included": bool(link and link.is_included),
                "value": link.value if link else "",
            })
        rows.append({"feature": feature, "cells": cells})

    return {"packages": packages, "rows": rows}


def global_addons() -> QuerySet:
    """Add-ons not tied to one service."""
    return (
        ServiceAddon.objects.filter(is_active=True, service__isnull=True)
        .visible().order_by("order", "pk")
    )


# --- staff reads -------------------------------------------------------------


def all_services() -> QuerySet:
    """Everything, including retired and hidden. For the admin list."""
    return (
        Service.objects.select_related("category")
        .annotate(
            feature_count=Count("features", distinct=True),
            package_count=Count("packages", distinct=True),
        )
        .order_by("order", "name")
    )


def service_for_edit(pk: int):  # noqa: ANN201
    return (
        Service.objects.select_related("category")
        .prefetch_related("features", "packages", "addons")
        .filter(pk=pk)
        .first()
    )
