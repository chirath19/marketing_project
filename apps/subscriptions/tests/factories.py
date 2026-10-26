"""Test helpers for client services."""

from __future__ import annotations

from apps.subscriptions.models import ClientSubscription, SubscriptionStatus

__all__ = ["make_service", "make_subscription"]


def make_service(name: str = "SEO growth retainer", *, category_slug: str = "search",
                 workspace_module: str = "seo", price="2400", **fields):  # noqa: ANN001, ANN201
    """A catalogue service in a category that unlocks a workspace module."""
    from decimal import Decimal

    from apps.catalog.models import Service, ServiceCategory

    category, _created = ServiceCategory.objects.get_or_create(
        slug=category_slug,
        defaults={"name": category_slug.title(), "order": 10,
                  "workspace_module": workspace_module},
    )
    if workspace_module and not category.workspace_module:
        category.workspace_module = workspace_module
        category.save(update_fields=["workspace_module"])

    # The catalogue is seeded by a migration, so a fixture that guessed a
    # slug would collide with a real row. Suffixed until it is free.
    base = fields.pop("slug", name.lower().replace(" ", "-").replace(":", ""))
    slug, suffix = base, 1
    while Service.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base}-{suffix}"

    return Service.objects.create(
        name=name, slug=slug, category=category,
        short_description=fields.pop("short_description", "A service."),
        price=Decimal(price) if price is not None else None,
        currency="USD", billing_type=fields.pop("billing_type", "monthly"),
        **fields,
    )


def make_subscription(organization, *, service=None, actor=None,  # noqa: ANN001
                      status: str = SubscriptionStatus.ACTIVE,
                      **fields) -> ClientSubscription:
    """A service attached to a client, built the way the real one is.

    Through the service layer rather than `objects.create`, so a test
    exercises the same path staff do — a row made directly would skip
    the history entry and the activation stamp, and would quietly prove
    less than it appears to.
    """
    from apps.subscriptions.services import create_subscription

    return create_subscription(
        organization=organization,
        service=service or make_service(),
        actor=actor,
        status=status,
        **fields,
    )
