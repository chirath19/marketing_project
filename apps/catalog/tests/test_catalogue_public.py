"""The public service catalogue."""

from decimal import Decimal

import pytest

from apps.catalog.models import BillingType, Service
from apps.catalog.tests.factories import (
    include_feature,
    make_addon,
    make_category,
    make_feature,
    make_package,
    make_service,
)

pytestmark = pytest.mark.django_db


# --- the seeded catalogue ----------------------------------------------------


def test_the_catalogue_renders(client):
    """Seeded by a migration, so a fresh install is not an empty shop."""
    response = client.get("/services/")

    assert response.status_code == 200
    assert b"SEO growth retainer" in response.content


def test_a_service_detail_page_renders(client):
    response = client.get("/services/seo-growth-retainer/")

    assert response.status_code == 200
    assert b"Monthly content" in response.content


def test_an_unknown_service_is_a_404(client):
    assert client.get("/services/no-such-service/").status_code == 404


# --- visibility and retirement -----------------------------------------------


def test_a_hidden_service_is_not_listed(client):
    make_service("Hidden service", is_visible=False)

    assert b"Hidden service" not in client.get("/services/").content


def test_a_hidden_service_detail_page_is_a_404(client):
    make_service("Hidden service", is_visible=False)

    assert client.get("/services/hidden-service/").status_code == 404


def test_a_retired_service_leaves_the_catalogue(client):
    """`is_active` is whether the agency still sells it; `is_visible` is
    whether it is on the page. Either one off takes it down."""
    make_service("Retired service", is_active=False)

    assert b"Retired service" not in client.get("/services/").content
    assert client.get("/services/retired-service/").status_code == 404


def test_a_retired_service_is_kept_not_deleted():
    service = make_service("Retired service", is_active=False)

    assert Service.objects.filter(pk=service.pk).exists()


# --- categories --------------------------------------------------------------


def test_a_category_page_shows_only_its_services(client):
    search = make_category("Search")
    paid = make_category("Paid", slug="paid", order=20)
    make_service("A search service", category=search)
    make_service("A paid service", category=paid, slug="a-paid-service")

    body = client.get("/services/category/search/").content

    assert b"A search service" in body
    assert b"A paid service" not in body


def test_an_empty_category_is_not_offered(client):
    """A filter that leads nowhere."""
    make_category("Nothing here", slug="nothing-here", order=99)

    assert b"Nothing here" not in client.get("/services/").content


def test_a_category_with_only_hidden_services_counts_as_empty(client):
    category = make_category("Quiet", slug="quiet", order=98)
    make_service("Invisible", category=category, is_visible=False)

    assert b"Quiet" not in client.get("/services/").content


def test_an_unknown_category_is_a_404(client):
    assert client.get("/services/category/nope/").status_code == 404


def test_the_active_category_is_marked_current(client):
    assert b'aria-current="page"' in client.get("/services/category/search/").content


# --- pricing -----------------------------------------------------------------


def test_a_monthly_price_reads_as_one(client):
    make_service("Monthly thing", price="1800", billing=BillingType.MONTHLY)

    body = client.get("/services/monthly-thing/").content

    assert b"$1,800" in body
    assert b"per month" in body


def test_a_one_off_price_reads_as_one(client):
    make_service("One off thing", price="1500", billing=BillingType.ONE_TIME)

    body = client.get("/services/one-off-thing/").content

    assert b"$1,500" in body
    assert b"one time" in body


def test_a_custom_priced_service_says_so_rather_than_showing_a_number(client):
    """Inventing a figure to fill the field would be worse than saying it
    cannot be priced yet."""
    make_service("Bespoke thing", price=None, billing=BillingType.CUSTOM)

    body = client.get("/services/bespoke-thing/").content

    assert b"Custom quote" in body


def test_whole_amounts_lose_their_decimals():
    """"$2,400" reads as a price; "$2,400.00" reads as an invoice line."""
    service = make_service("Round", price="2400")

    assert service.price_display == "$2,400"


def test_a_part_amount_keeps_its_decimals():
    service = make_service("Precise", price="99.50")

    assert service.price_display == "$99.50"


def test_a_priced_billing_type_requires_a_number():
    from django.core.exceptions import ValidationError

    service = Service(name="Broken", slug="broken",
                      category=make_category(), short_description="x",
                      price=None, billing_type=BillingType.MONTHLY)

    with pytest.raises(ValidationError) as error:
        service.full_clean()

    assert "price" in error.value.message_dict


def test_a_custom_quote_must_not_carry_a_price():
    from django.core.exceptions import ValidationError

    service = Service(name="Confused", slug="confused",
                      category=make_category(), short_description="x",
                      price=Decimal("100"), billing_type=BillingType.CUSTOM)

    with pytest.raises(ValidationError) as error:
        service.full_clean()

    assert "price" in error.value.message_dict


# --- packages and comparison --------------------------------------------------


def test_two_packages_produce_a_comparison_table(client):
    service = make_service("Tiered")
    feature = make_feature(service, "Monthly reporting")
    starter = make_package(service, "Starter", price="1000")
    growth = make_package(service, "Growth", price="2000", order=20)
    include_feature(starter, feature, is_included=False)
    include_feature(growth, feature, is_included=True)

    body = client.get("/services/tiered/").content

    assert b"Compare packages" in body
    assert b"Monthly reporting" in body
    assert b"Not included" in body
    assert b"Included" in body


def test_one_package_is_not_a_comparison(client):
    service = make_service("Single tier")
    make_feature(service, "Something")
    make_package(service, "Only tier")

    body = client.get("/services/single-tier/").content

    assert b"Compare packages" not in body
    assert b"Only tier" in body


def test_a_comparison_cell_can_carry_a_value_instead_of_a_tick(client):
    """A grid of ticks says less than "2 channels" against "4 channels"."""
    service = make_service("Tiered")
    feature = make_feature(service, "Channels")
    starter = make_package(service, "Starter")
    growth = make_package(service, "Growth", order=20)
    include_feature(starter, feature, value="2 channels")
    include_feature(growth, feature, value="4 channels")

    body = client.get("/services/tiered/").content

    assert b"2 channels" in body
    assert b"4 channels" in body


def test_a_recommended_package_is_marked(client):
    service = make_service("Tiered")
    make_feature(service, "Something")
    make_package(service, "Starter")
    make_package(service, "Growth", order=20, is_recommended=True)

    assert b"Recommended" in client.get("/services/tiered/").content


def test_a_hidden_package_is_not_shown(client):
    service = make_service("Tiered")
    make_feature(service, "Something")
    make_package(service, "Visible tier")
    make_package(service, "Hidden tier", order=20, is_visible=False)

    body = client.get("/services/tiered/").content

    assert b"Visible tier" in body
    assert b"Hidden tier" not in body


def test_a_package_cannot_include_another_services_feature():
    from django.core.exceptions import ValidationError

    from apps.catalog.models import PackageFeature

    first = make_service("First")
    second = make_service("Second", slug="second")
    package = make_package(first, "Tier")
    foreign = make_feature(second, "Not ours")

    link = PackageFeature(package=package, feature=foreign)

    with pytest.raises(ValidationError):
        link.full_clean()


# --- add-ons -----------------------------------------------------------------


def test_a_service_addon_shows_on_its_service(client):
    service = make_service("With addon")
    make_addon("Extra thing", service=service)

    assert b"Extra thing" in client.get("/services/with-addon/").content


def test_a_global_addon_shows_on_the_catalogue(client):
    make_addon("Anything addon", slug="anything-addon")

    assert b"Anything addon" in client.get("/services/").content


def test_a_retired_addon_is_not_shown(client):
    make_addon("Gone addon", slug="gone-addon", is_active=False)

    assert b"Gone addon" not in client.get("/services/").content


# --- performance --------------------------------------------------------------


def test_the_catalogue_costs_a_fixed_number_of_queries(
    client, django_assert_max_num_queries
):
    """Features and packages are prefetched, so twelve services is not
    fifty queries.

    The budget rose by one when the catalogue gained its editable
    introduction: one lookup for the CMS page that supplies the heading
    and intro copy. That is the whole cost of making the page's framing
    editable instead of hard-coded, and it is worth it.

    It rose by one more when every public page gained the `tracking_settings`
    context processor: one lookup for the site-wide tag configuration row,
    needed to decide whether GTM/GA4/Pixel/RudderStack snippets render at
    all. Seeded via migration, so it is always a single `SELECT`.
    """
    # Operating mode and editable copy add fixed lookups; disabled tracking removes one.
    with django_assert_max_num_queries(17):
        assert client.get("/services/").status_code == 200


# --- SEO ----------------------------------------------------------------------


def test_a_service_uses_its_own_meta_title(client):
    make_service("Plain", meta_title="UNIQUE SERVICE SEO TITLE")

    assert b"UNIQUE SERVICE SEO TITLE" in client.get("/services/plain/").content


def test_a_service_falls_back_to_its_short_description(client):
    make_service("Fallback", short_description="A SHORT DESCRIPTION OF IT")

    assert b"A SHORT DESCRIPTION OF IT" in client.get("/services/fallback/").content


def test_a_priced_service_carries_offer_structured_data(client):
    make_service("Priced", price="1800")

    body = client.get("/services/priced/").content

    assert b'"@type": "Service"' in body
    assert b'"priceCurrency"' in body


def test_a_custom_quote_carries_no_price_in_structured_data(client):
    """Stating a price we do not have would be worse than stating none."""
    make_service("Bespoke", price=None, billing=BillingType.CUSTOM)

    body = client.get("/services/bespoke/").content

    assert b'"@type": "Service"' not in body


def test_catalogue_content_is_escaped(client):
    make_service("Risky", short_description="<script>alert(1)</script>")

    body = client.get("/services/risky/").content

    assert b"<script>alert(1)</script>" not in body
    assert b"&lt;script&gt;" in body
