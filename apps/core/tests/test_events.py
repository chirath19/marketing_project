"""The event bus is the seam that keeps domains from importing each other,
so its failure behaviour matters as much as its happy path."""

import pytest
from django.db import transaction

from apps.core.events import DomainEvent, EventBus


@pytest.fixture
def bus():
    bus = EventBus()
    yield bus
    bus.clear()


def test_handler_receives_published_event(bus):
    received = []
    bus.subscribe("quote.requested", received.append)

    bus.publish_now(DomainEvent("quote.requested", {"quote_id": 7}))

    assert len(received) == 1
    assert received[0].payload == {"quote_id": 7}


def test_only_matching_handlers_are_called(bus):
    quotes, leads = [], []
    bus.subscribe("quote.requested", quotes.append)
    bus.subscribe("lead.created", leads.append)

    bus.publish_now(DomainEvent("lead.created"))

    assert quotes == []
    assert len(leads) == 1


def test_subscribing_the_same_handler_twice_does_not_double_deliver(bus):
    received = []
    bus.subscribe("x", received.append)
    bus.subscribe("x", received.append)

    bus.publish_now(DomainEvent("x"))

    assert len(received) == 1


def test_unsubscribe_stops_delivery(bus):
    received = []
    bus.subscribe("x", received.append)
    bus.unsubscribe("x", received.append)

    bus.publish_now(DomainEvent("x"))

    assert received == []


def test_a_failing_handler_does_not_stop_the_others(bus):
    """A notification that cannot be written must not undo the business
    operation that caused it, nor block unrelated subscribers."""
    survived = []

    def explodes(event):
        raise RuntimeError("handler is broken")

    bus.subscribe("x", explodes)
    bus.subscribe("x", survived.append)

    bus.publish_now(DomainEvent("x"))

    assert len(survived) == 1


@pytest.mark.django_db(transaction=True)
def test_publish_waits_for_the_transaction_to_commit(bus):
    """Handlers must not see state that is later rolled back."""
    received = []
    bus.subscribe("x", received.append)

    with transaction.atomic():
        bus.publish(DomainEvent("x"))
        assert received == [], "dispatched before commit"

    assert len(received) == 1


@pytest.mark.django_db(transaction=True)
def test_publish_is_discarded_when_the_transaction_rolls_back(bus):
    received = []
    bus.subscribe("x", received.append)

    with pytest.raises(ValueError), transaction.atomic():
        bus.publish(DomainEvent("x"))
        raise ValueError("business rule failed")

    assert received == []
