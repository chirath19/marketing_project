"""Test helpers for the catalogue."""

from __future__ import annotations

from decimal import Decimal

from django.utils.text import slugify

from apps.catalog.models import (
    BillingType,
    PackageFeature,
    Service,
    ServiceAddon,
    ServiceCategory,
    ServiceFeature,
    ServicePackage,
)

__all__ = ["make_category", "make_service", "make_feature", "make_package",
           "make_addon", "include_feature"]


def make_category(name: str = "Search", **fields) -> ServiceCategory:
    """A category, reusing one of the seeded ones if the name matches.

    The seed migration ships Search, Paid, Social, Email and Analytics, so
    a test naming one of those should get that category rather than fail
    on the unique constraint.
    """
    defaults = {"slug": slugify(name), "order": 10}
    defaults.update(fields)
    category, _created = ServiceCategory.objects.get_or_create(
        name=name, defaults=defaults,
    )
    return category


def make_service(name: str = "SEO retainer", *, category=None,  # noqa: ANN001
                 price="2400", billing: str = BillingType.MONTHLY,
                 **fields) -> Service:
    defaults = {
        "slug": slugify(name),
        "category": category or make_category(),
        "short_description": "Does useful things.",
        "price": Decimal(price) if price is not None else None,
        "billing_type": billing,
        "order": 10,
    }
    defaults.update(fields)
    return Service.objects.create(name=name, **defaults)


def make_feature(service: Service, label: str = "A feature", **fields) -> ServiceFeature:
    defaults = {"order": 10}
    defaults.update(fields)
    return ServiceFeature.objects.create(service=service, label=label, **defaults)


def make_package(service: Service, name: str = "Starter", *, price="1000",
                 **fields) -> ServicePackage:
    defaults = {
        "slug": slugify(name),
        "price": Decimal(price) if price is not None else None,
        "billing_type": BillingType.MONTHLY,
        "order": 10,
    }
    defaults.update(fields)
    return ServicePackage.objects.create(service=service, name=name, **defaults)


def include_feature(package: ServicePackage, feature: ServiceFeature,
                    **fields) -> PackageFeature:
    return PackageFeature.objects.create(package=package, feature=feature, **fields)


def make_addon(name: str = "Landing page", *, service=None, **fields) -> ServiceAddon:  # noqa: ANN001
    defaults = {
        "slug": slugify(name), "price": Decimal("500"),
        "billing_type": BillingType.ONE_TIME, "order": 10,
    }
    defaults.update(fields)
    return ServiceAddon.objects.create(name=name, service=service, **defaults)
