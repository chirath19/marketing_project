"""The quote selection a visitor builds.

Kept in the session, resolved against the live catalogue on every read —
so a selection cannot quote a price that has since changed, and a
withdrawn service drops out of it on its own.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.catalog.models import BillingType
from apps.catalog.tests.factories import make_feature, make_package, make_service

pytestmark = pytest.mark.django_db


def add(client, service, package=None):  # noqa: ANN001
    data = {"service": service.pk}
    if package is not None:
        data["package"] = package.pk
    return client.post(reverse("public:quote_add"), data)


# --- adding and removing ------------------------------------------------------


def test_a_service_can_be_added(client):
    service = make_service("Addable")

    add(client, service)
    response = client.get("/quote/")

    assert b"Addable" in response.content


def test_an_empty_selection_says_so(client):
    response = client.get("/quote/")

    assert response.status_code == 200
    assert b"Your quote is empty" in response.content


def test_a_package_can_be_chosen_instead_of_the_service(client):
    service = make_service("Tiered")
    package = make_package(service, "Growth", price="3800")

    add(client, service, package)
    body = client.get("/quote/").content

    assert b"Tiered &mdash; Growth" in body or b"Growth" in body
    assert b"$3,800" in body


def test_choosing_a_different_tier_replaces_the_first(client):
    """Nobody wants two tiers of the same service on one quote."""
    service = make_service("Tiered")
    starter = make_package(service, "Starter", price="1000")
    growth = make_package(service, "Growth", price="2000", order=20)

    add(client, service, starter)
    add(client, service, growth)

    response = client.get("/quote/")
    assert len(response.context["lines"]) == 1
    assert b"$2,000" in response.content


def test_a_line_can_be_removed(client):
    service = make_service("Removable")
    add(client, service)

    client.post(reverse("public:quote_remove"), {"key": f"{service.pk}:"})

    assert b"Your quote is empty" in client.get("/quote/").content


def test_the_selection_can_be_cleared(client):
    add(client, make_service("One"))
    add(client, make_service("Two", slug="two"))

    client.post(reverse("public:quote_clear"))

    assert client.get("/quote/").context["lines"] == []


# --- what cannot be added -----------------------------------------------------


def test_a_hidden_service_cannot_be_added(client):
    service = make_service("Hidden", is_visible=False)

    assert add(client, service).status_code == 404


def test_a_retired_service_cannot_be_added(client):
    service = make_service("Retired", is_active=False)

    assert add(client, service).status_code == 404


def test_a_service_marked_unavailable_for_quotes_cannot_be_added(client):
    """Some things are only sold as part of something else."""
    service = make_service("Bundled only", can_request_quote=False)

    assert add(client, service).status_code == 404


def test_a_package_of_another_service_cannot_be_added(client):
    """The package id is posted, so this is the obvious thing to try."""
    first = make_service("First")
    second = make_service("Second", slug="second")
    foreign = make_package(second, "Their tier")

    assert add(client, first, foreign).status_code == 404


def test_a_nonsense_service_id_is_a_404(client):
    response = client.post(reverse("public:quote_add"), {"service": "banana"})

    assert response.status_code == 404


def test_adding_is_post_only(client):
    """Adding changes state, so it must not be reachable by a link a
    crawler or a prefetch can follow."""
    service = make_service("Addable")

    response = client.get(reverse("public:quote_add"), {"service": service.pk})

    assert response.status_code == 405


def test_the_selection_is_capped(client):
    """So a crafted request cannot grow a session unboundedly."""
    from apps.catalog.quote_selection import MAX_ITEMS

    for index in range(MAX_ITEMS + 5):
        add(client, make_service(f"Service {index}", slug=f"service-{index}"))

    assert len(client.get("/quote/").context["lines"]) <= MAX_ITEMS


# --- the selection stays honest ----------------------------------------------


def test_a_service_retired_after_selection_drops_out(client):
    """The session holds identifiers; everything shown is resolved from
    the live catalogue, so a withdrawn service cannot linger."""
    service = make_service("Withdrawn")
    add(client, service)
    assert len(client.get("/quote/").context["lines"]) == 1

    service.is_active = False
    service.save(update_fields=["is_active"])

    assert client.get("/quote/").context["lines"] == []


def test_a_price_change_is_reflected_immediately(client):
    service = make_service("Repriced", price="1000")
    add(client, service)
    assert b"$1,000" in client.get("/quote/").content

    service.price = Decimal("1500")
    service.save(update_fields=["price"])

    assert b"$1,500" in client.get("/quote/").content


def test_a_deleted_package_keeps_the_service_in_the_selection(client):
    """Losing the whole line because a tier was renamed would be worse
    than falling back to the service."""
    service = make_service("Tiered")
    package = make_package(service, "Going away")
    add(client, service, package)

    package.delete()

    lines = client.get("/quote/").context["lines"]
    assert len(lines) == 1
    assert lines[0].package is None


# --- totals -------------------------------------------------------------------


def test_monthly_and_one_off_are_totalled_separately(client):
    """Adding them would produce a number that means nothing."""
    make_service("Monthly", price="1000", billing=BillingType.MONTHLY)
    make_service("One off", slug="one-off", price="500",
                 billing=BillingType.ONE_TIME)

    from apps.catalog.models import Service
    add(client, Service.objects.get(slug="monthly"))
    add(client, Service.objects.get(slug="one-off"))

    totals = client.get("/quote/").context["totals"]

    assert totals.monthly == Decimal("1000")
    assert totals.one_time == Decimal("500")


def test_a_custom_priced_service_is_flagged_rather_than_counted(client):
    """A total presented as complete when it is not would be misleading."""
    make_service("Priced", price="1000")
    make_service("Bespoke", slug="bespoke", price=None,
                 billing=BillingType.CUSTOM)

    from apps.catalog.models import Service
    add(client, Service.objects.get(slug="priced"))
    add(client, Service.objects.get(slug="bespoke"))

    response = client.get("/quote/")

    assert response.context["totals"].has_custom
    assert response.context["totals"].monthly == Decimal("1000")
    assert b"not the whole picture" in response.content


def test_the_total_is_described_as_indicative(client):
    add(client, make_service("Anything"))

    assert b"Indicative only" in client.get("/quote/").content


# --- sending it on ------------------------------------------------------------


def test_the_selection_can_be_sent_by_email(client):
    """The platform sends nothing itself; the summary travels in a mailto
    the visitor sends from their own address."""
    from apps.cms.tests.factories import site_settings

    site_settings(contact_email="hello@agency.example")
    add(client, make_service("Sendable"))

    body = client.get("/quote/").content

    assert b"mailto:hello@agency.example" in body
    assert b"Sendable" in body


def test_the_selection_can_be_sent_by_whatsapp(client):
    from apps.cms.tests.factories import site_settings

    site_settings(whatsapp_number="94771234567")
    add(client, make_service("Sendable"))

    assert b"wa.me/94771234567" in client.get("/quote/").content


def test_the_quote_page_is_not_indexed(client):
    """One visitor's selection is not a page for a search engine."""
    assert b"noindex" in client.get("/quote/").content


# --- the catalogue's own add buttons -----------------------------------------


def test_the_catalogue_offers_an_add_button(client):
    make_service("Addable")

    assert b"Add to quote" in client.get("/services/").content


def test_a_service_not_available_for_quotes_offers_no_button(client):
    service = make_service("Bundled only", can_request_quote=False)
    make_feature(service, "Something")

    body = client.get("/services/bundled-only/").content.decode()

    # Scoped to this service's own purchase panel. Related services
    # shown further down the page are quotable in their own right, and
    # their buttons are correct — a bare "not in body" would fail on
    # those and claim a bug that is not there.
    panel = body.split("<aside")[1].split("</aside>")[0]
    assert "Add to quote" not in panel
    assert "Sold as part of another service" in panel


# --- persistent selection controls and inline additions -----------------------


def quote_controls(response, service, package=None):
    from html.parser import HTMLParser

    class Controls(HTMLParser):
        active = False
        button = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "form":
                self.active = (
                    attrs.get("data-service") == str(service.pk)
                    and attrs.get("data-package") == (str(package.pk) if package else "")
                )
            if tag == "button" and self.active:
                self.button = attrs

        def handle_endtag(self, tag):
            if tag == "form":
                self.active = False

    parser = Controls()
    parser.feed(response.content.decode())
    return parser.button


def test_selected_service_is_marked_on_catalogue_category_and_related_cards(client):
    service = make_service("Selected")
    other = make_service("Related", slug="related", category=service.category)
    add(client, service)

    for url in ["/services/", service.category.get_absolute_url(),
                service.get_absolute_url(), other.get_absolute_url()]:
        response = client.get(url)
        control = quote_controls(response, service)
        assert control["data-selected"] == "true"
        assert "disabled" in control
        assert b"Already added" in response.content
        assert b"add again" not in response.content


@pytest.mark.parametrize("with_comparison", [False, True])
def test_only_the_chosen_package_is_marked(client, with_comparison):
    service = make_service("Tiered")
    starter = make_package(service, "Starter")
    growth = make_package(service, "Growth", order=20)
    if with_comparison:
        make_feature(service, "Reporting")
    add(client, service, starter)

    response = client.get(service.get_absolute_url())
    assert "disabled" in quote_controls(response, service)
    assert "disabled" in quote_controls(response, service, starter)
    assert "disabled" not in quote_controls(response, service, growth)


@pytest.mark.parametrize("clear", [False, True])
def test_removing_or_clearing_restores_add_button(client, clear):
    service = make_service("Removable")
    add(client, service)
    if clear:
        client.post(reverse("public:quote_clear"))
    else:
        client.post(reverse("public:quote_remove"), {"key": f"{service.pk}:"})
    assert "disabled" not in quote_controls(client.get("/services/"), service)


def test_readding_from_card_preserves_package_and_quote_order(client):
    first = make_service("First")
    package = make_package(first)
    second = make_service("Second", slug="second")
    add(client, first, package)
    add(client, second)
    add(client, first)
    lines = client.get("/quote/").context["lines"]
    assert [line.service.pk for line in lines] == [first.pk, second.pk]
    assert lines[0].package.pk == package.pk


def test_inline_add_returns_saved_state_without_queued_flash_message(client):
    service = make_service("Inline")
    response = client.post(reverse("public:quote_add"), {"service": service.pk},
                           HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    assert response.json()["selection"] == {str(service.pk): ""}
    assert response.json()["count"] == 1
    assert list(client.get("/services/").context["messages"]) == []
    state = client.get("/quote/", HTTP_ACCEPT="application/json")
    assert state.json()["selection"] == response.json()["selection"]
    assert state["Cache-Control"] == "no-store"


def test_inline_limit_failure_does_not_report_service_as_added(client):
    from apps.catalog.quote_selection import MAX_ITEMS, SESSION_KEY

    session = client.session
    session[SESSION_KEY] = [f"{100000 + index}:" for index in range(MAX_ITEMS)]
    session.save()
    service = make_service("Overflow")
    response = client.post(reverse("public:quote_add"), {"service": service.pk},
                           HTTP_ACCEPT="application/json")
    assert response.status_code == 409
    assert str(service.pk) not in response.json()["selection"]
    assert response.json()["count"] == MAX_ITEMS


@pytest.mark.parametrize("destination", ["https://outside.example/", "//outside.example/"])
def test_return_path_cannot_redirect_to_another_site(client, destination):
    service = make_service("Safe return")
    response = client.post(reverse("public:quote_add"), {
        "service": service.pk, "next": destination,
    })
    assert response.url == reverse("public:quote")


def test_without_javascript_add_returns_to_the_service_anchor(client):
    service = make_service("Anchor")
    destination = f"/services/?category=search#quote-service-{service.pk}"
    response = client.post(reverse("public:quote_add"), {
        "service": service.pk, "next": destination,
    })
    assert response.url == destination


def test_invalid_package_is_not_silently_added_as_base_service(client):
    service = make_service("Tiered")
    response = client.post(reverse("public:quote_add"), {
        "service": service.pk, "package": "invalid",
    }, HTTP_ACCEPT="application/json")
    assert response.status_code == 404
    assert client.get("/quote/").context["lines"] == []


def test_inline_add_still_requires_csrf():
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    service = make_service("Protected")
    response = client.post(reverse("public:quote_add"), {"service": service.pk},
                           HTTP_ACCEPT="application/json")
    assert response.status_code == 403
