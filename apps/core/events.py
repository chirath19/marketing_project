"""A synchronous, in-process domain event bus.

Why this exists: the brief forbids business logic in signals, and the
modular monolith forbids one domain importing another's internals. A
domain publishes a fact ("a quote was requested"); interested domains —
notifications, audit — subscribe. Neither side imports the other.

Delivery is synchronous and deliberately deferred to
`transaction.on_commit`, so a handler can never react to a change that
later rolls back. Handler failures are logged and swallowed: a
notification that could not be written must not undo the business
operation that caused it. Anything that genuinely must not be lost is
written to the outbox table inside the same transaction instead.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """A fact that has already happened. Past tense, immutable."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


Handler = Callable[[DomainEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        if handler not in self._handlers[event_name]:
            self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Handler) -> None:
        if handler in self._handlers[event_name]:
            self._handlers[event_name].remove(handler)

    def handlers_for(self, event_name: str) -> list[Handler]:
        return list(self._handlers[event_name])

    def clear(self) -> None:
        """Reset the registry. Test support only."""
        self._handlers.clear()

    def publish(self, event: DomainEvent) -> None:
        """Queue an event for dispatch once the current transaction commits."""
        transaction.on_commit(lambda: self._dispatch(event))

    def publish_now(self, event: DomainEvent) -> None:
        """Dispatch immediately, bypassing the commit hook.

        Only for callers that are not inside a transaction, such as a
        management command doing read-only work.
        """
        self._dispatch(event)

    def _dispatch(self, event: DomainEvent) -> None:
        for handler in self._handlers[event.name]:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Event handler %s failed for event %s",
                    getattr(handler, "__qualname__", repr(handler)),
                    event.name,
                )


bus = EventBus()


def subscribe(event_name: str) -> Callable[[Handler], Handler]:
    """Decorator form: register a handler at import time."""

    def decorator(handler: Handler) -> Handler:
        bus.subscribe(event_name, handler)
        return handler

    return decorator
