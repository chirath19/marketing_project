"""The visitor's quote selection.

Kept in the session, not the database. A visitor browsing the catalogue
has not asked for an account and has not agreed to anything being stored
about them; a row per abandoned basket would be data the agency neither
needs nor wants to be responsible for.

The session holds only identifiers. Everything shown — name, price,
whether the service still exists — is resolved from the catalogue on each
read, so a selection made last week cannot quote a price that has since
changed, and a retired service drops out of it on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.http import HttpRequest

SESSION_KEY = "quote_selection"

#: A cap, so a crafted request cannot grow a session unboundedly.
MAX_ITEMS = 25


@dataclass(frozen=True, slots=True)
class SelectionLine:
    service: object
    package: object | None

    @property
    def key(self) -> str:
        return _key(self.service.pk, getattr(self.package, "pk", None))

    @property
    def name(self) -> str:
        if self.package is not None:
            return f"{self.service.name} — {self.package.name}"
        return self.service.name

    @property
    def priced(self):  # noqa: ANN201
        """Whichever of the two carries the price."""
        return self.package if self.package is not None else self.service


def _key(service_id: int, package_id: int | None) -> str:
    return f"{service_id}:{package_id or ''}"


def _raw(request: HttpRequest) -> list[str]:
    value = request.session.get(SESSION_KEY)
    return value if isinstance(value, list) else []


def _store(request: HttpRequest, keys: list[str]) -> None:
    request.session[SESSION_KEY] = keys[:MAX_ITEMS]
    request.session.modified = True


def add(request: HttpRequest, service_id: int, package_id: int | None = None) -> bool:
    """Add a service, optionally a specific package.

    Choosing a different package of a service already selected replaces
    it rather than adding a second line: nobody wants two tiers of the
    same thing on one quote.
    """
    keys = _raw(request)[:]
    for index, key in enumerate(keys):
        if key.startswith(f"{service_id}:"):
            # A catalogue card must not reset an explicitly chosen tier.
            # Tier changes keep the service in its original position.
            if package_id is not None and key != _key(service_id, package_id):
                keys[index] = _key(service_id, package_id)
                _store(request, keys)
            return True

    if len(keys) >= MAX_ITEMS:
        return False

    keys.append(_key(service_id, package_id))
    _store(request, keys)
    return True


def remove(request: HttpRequest, key: str) -> None:
    _store(request, [existing for existing in _raw(request) if existing != key])


def clear(request: HttpRequest) -> None:
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True


def contains_service(request: HttpRequest, service_id: int) -> bool:
    return any(key.startswith(f"{service_id}:") for key in _raw(request))


def selection_state(request: HttpRequest) -> dict[str, str]:
    """Identifiers for public controls, without a query per service card."""
    return {key.partition(":")[0]: key.partition(":")[2] for key in _raw(request)}


def count(request: HttpRequest) -> int:
    """How many lines are selected.

    Counts the raw keys rather than resolving them: this runs on every
    page to render the header badge, and a count is not worth a query.
    """
    return len(_raw(request))


def lines(request: HttpRequest) -> list[SelectionLine]:
    """The selection, resolved against the live catalogue.

    Anything that has since been retired, hidden or deleted is dropped —
    and the session is rewritten without it, so it does not keep being
    looked up.
    """
    from apps.catalog.selectors import live_services

    raw = _raw(request)
    if not raw:
        return []

    wanted: dict[int, int | None] = {}
    for key in raw:
        service_part, _, package_part = key.partition(":")
        if not service_part.isdigit():
            continue
        wanted[int(service_part)] = int(package_part) if package_part.isdigit() else None

    services = {
        service.pk: service
        for service in live_services().filter(pk__in=wanted, can_request_quote=True)
    }

    resolved: list[SelectionLine] = []
    surviving: list[str] = []

    for key in raw:
        service_part, _, package_part = key.partition(":")
        service = services.get(int(service_part)) if service_part.isdigit() else None
        if service is None:
            continue

        package = None
        if package_part.isdigit():
            package = next(
                (candidate for candidate in service.packages.all()
                 if candidate.pk == int(package_part)),
                None,
            )
            if package is None:
                # The tier is gone but the service remains; keep the
                # service rather than silently dropping the whole line.
                package = None

        resolved.append(SelectionLine(service=service, package=package))
        surviving.append(_key(service.pk, getattr(package, "pk", None)))

    if surviving != raw:
        _store(request, surviving)

    return resolved


@dataclass(frozen=True, slots=True)
class Totals:
    monthly: Decimal
    one_time: Decimal
    currency: str
    has_custom: bool


def totals(selection: list[SelectionLine]) -> Totals:
    """What the selection adds up to.

    Monthly and one-off are kept apart, because adding them would produce
    a number that means nothing. Anything custom-priced is excluded and
    flagged, so the total is never presented as complete when it is not.
    """
    from apps.catalog.models import BillingType

    monthly = Decimal("0")
    one_time = Decimal("0")
    currency = ""
    has_custom = False

    for line in selection:
        priced = line.priced
        if priced.price is None:
            has_custom = True
            continue

        currency = currency or priced.currency
        if priced.billing_type == BillingType.MONTHLY:
            monthly += priced.price
        elif priced.billing_type == BillingType.ONE_TIME:
            one_time += priced.price

    return Totals(monthly=monthly, one_time=one_time,
                  currency=currency or "USD", has_custom=has_custom)
