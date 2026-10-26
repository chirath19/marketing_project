"""The client portal: navigation driven by entitlement, and enforced.

The brief's own words: *the dashboard must not merely hide unauthorized
modules; backend permissions must prevent direct URL access.* So the
tests here come in pairs — one asserting a module is absent from the
navigation, and one asserting the route behind it refuses the request.
A menu that hides a link while the view still serves the page is not
access control, it is decoration.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.core.modules import ALWAYS, ANY_SERVICE, PORTAL_MODULES, SERVICE
from apps.organizations.tests.factories import make_member, make_org
from apps.staff.tests.factories import PASSWORD, make_super_admin_user
from apps.subscriptions import selectors
from apps.subscriptions.guards import entitlement_keys
from apps.subscriptions.models import SubscriptionStatus
from apps.subscriptions.services import change_status
from apps.subscriptions.tests.factories import make_service, make_subscription

pytestmark = pytest.mark.django_db


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


def portal_url(key: str) -> str:
    return reverse("organizations:portal_module", args=[key])


@pytest.fixture(autouse=True)
def enabled_optional_analytics(db):
    from apps.core.models import OperatingSettings

    OperatingSettings.objects.filter(pk=1).update(analytics_enabled=True)


@pytest.fixture
def admin():
    return make_super_admin_user("boss@heliograph.agency")


def _client_with(admin, *, categories):  # noqa: ANN001, ANN202
    """A client organization with an active service per category given."""
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)

    modules = {
        "search": "seo",
        "paid": "paid_ads",
        "social": "social",
        "email": "email_marketing",
        "analytics": "analytics",
    }
    for slug in categories:
        make_subscription(
            org,
            actor=admin,
            service=make_service(
                f"{slug.title()} service", category_slug=slug, workspace_module=modules[slug]
            ),
            status=SubscriptionStatus.ACTIVE,
        )
    return org, user


# ---------------------------------------------------------------------------
# The navigation follows what they bought
# ---------------------------------------------------------------------------


def test_a_client_with_no_services_gets_only_account_modules(admin):
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)

    keys = entitlement_keys(user)

    assert keys == {
        "overview",
        "services",
        "quotes",
        "messages",
        "people",
        "settings",
        "reports",
        "receipts",
        "invoices",
        "service_requests",
    }
    assert "seo" not in keys
    assert "campaigns" not in keys, "nothing to put on it yet"


def test_an_seo_only_client_sees_the_brief_s_example(admin):
    """The brief's own example: Overview, Campaigns, SEO, Reports,
    Approvals, Messages."""
    _org, user = _client_with(admin, categories=["search"])

    keys = entitlement_keys(user)

    for expected in ("overview", "campaigns", "seo", "reports", "approvals", "messages"):
        assert expected in keys, expected
    for absent in ("paid_ads", "social", "email_marketing", "analytics"):
        assert absent not in keys, absent


def test_a_paid_and_social_client_sees_the_other_example(admin):
    _org, user = _client_with(admin, categories=["paid", "social"])

    keys = entitlement_keys(user)

    for expected in (
        "overview",
        "campaigns",
        "paid_ads",
        "social",
        "reports",
        "approvals",
        "messages",
    ):
        assert expected in keys, expected
    assert "seo" not in keys
    assert "email_marketing" not in keys


def test_specialist_areas_are_reached_from_the_entitled_project(client, admin):
    _org, user = _client_with(admin, categories=["search"])
    sign_in(client, user)

    body = client.get(reverse("organizations:overview")).content.decode()

    assert reverse("organizations:services") in body
    assert portal_url("seo") not in body  # Specialist tools are inside the project.
    subscription = selectors.subscriptions_for_client(user).first()
    detail = client.get(
        reverse("organizations:service_detail", args=[subscription.pk])
    ).content.decode()
    assert portal_url("seo") in detail
    assert portal_url("paid_ads") not in detail
    assert portal_url("social") not in detail


def test_buying_another_service_adds_its_module(admin):
    org, user = _client_with(admin, categories=["search"])
    assert "paid_ads" not in entitlement_keys(user)

    make_subscription(
        org,
        actor=admin,
        service=make_service("Google Ads", category_slug="paid", workspace_module="paid_ads"),
        status=SubscriptionStatus.ACTIVE,
    )

    assert "paid_ads" in entitlement_keys(user)


def test_pausing_a_service_removes_its_module_again(admin):
    org, user = _client_with(admin, categories=["search"])
    subscription = org.subscriptions_clientsubscription_set.get()
    assert "seo" in entitlement_keys(user)

    change_status(subscription=subscription, status=SubscriptionStatus.PAUSED, actor=admin)

    assert "seo" not in entitlement_keys(user)
    assert "campaigns" not in entitlement_keys(user), "nothing is running"


# ---------------------------------------------------------------------------
# And the routes enforce it
# ---------------------------------------------------------------------------


def test_a_module_they_have_not_bought_is_refused_by_url(client, admin):
    """The point of the phase. Hiding the link is not the control."""
    _org, user = _client_with(admin, categories=["search"])
    sign_in(client, user)

    assert client.get(portal_url("seo")).status_code == 200
    assert client.get(portal_url("paid_ads")).status_code == 403
    assert client.get(portal_url("social")).status_code == 403
    assert client.get(portal_url("email_marketing")).status_code == 403


def test_a_client_with_nothing_is_refused_every_delivery_module(client, admin):
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)
    sign_in(client, user)

    for key in (
        "campaigns",
        "seo",
        "paid_ads",
        "social",
        "email_marketing",
        "analytics",
        "approvals",
    ):
        assert client.get(portal_url(key)).status_code == 403, key


def test_pausing_a_service_closes_the_route_not_just_the_link(client, admin):
    """A stale bookmark, or a tab left open, must meet the same rule."""
    org, user = _client_with(admin, categories=["paid"])
    sign_in(client, user)
    assert client.get(portal_url("paid_ads")).status_code == 200

    subscription = org.subscriptions_clientsubscription_set.get()
    change_status(subscription=subscription, status=SubscriptionStatus.PAUSED, actor=admin)

    assert client.get(portal_url("paid_ads")).status_code == 403


def test_a_pending_service_opens_nothing(client, admin):
    """Agreed is not the same as running."""
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)
    make_subscription(
        org,
        actor=admin,
        service=make_service("SEO", category_slug="search"),
        status=SubscriptionStatus.PENDING,
    )
    sign_in(client, user)

    assert "seo" not in entitlement_keys(user)
    assert client.get(portal_url("seo")).status_code == 403


def test_an_anonymous_visitor_is_sent_to_sign_in(client):
    response = client.get(portal_url("seo"))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_an_unknown_module_is_a_404(client, admin):
    _org, user = _client_with(admin, categories=["search"])
    sign_in(client, user)

    assert client.get(portal_url("nonsense")).status_code == 404


def test_an_account_module_has_its_own_page_not_the_generic_one(client, admin):
    """`/area/overview/` is a 404: Overview has a real page of its own,
    and two addresses for one screen is a trap for whoever maintains it."""
    _org, user = _client_with(admin, categories=["search"])
    sign_in(client, user)

    assert client.get(portal_url("overview")).status_code == 404
    assert client.get(portal_url("services")).status_code == 404


def test_one_clients_entitlement_never_opens_anothers_module(client, admin):
    """Org B pays for ads. That must not open the ads area for org A."""
    org_a = make_org("Vantage Interiors")
    user_a = make_user(email="a@vantage.example")
    make_member(org_a, user_a)
    make_subscription(
        org_a,
        actor=admin,
        service=make_service("SEO", category_slug="search"),
        status=SubscriptionStatus.ACTIVE,
    )

    org_b = make_org("Northwind Supply")
    user_b = make_user(email="b@northwind.example")
    make_member(org_b, user_b)
    make_subscription(
        org_b,
        actor=admin,
        service=make_service("Google Ads", category_slug="paid", workspace_module="paid_ads"),
        status=SubscriptionStatus.ACTIVE,
    )

    sign_in(client, user_a)

    assert client.get(portal_url("seo")).status_code == 200
    assert client.get(portal_url("paid_ads")).status_code == 403


# ---------------------------------------------------------------------------
# The registry and the routes agree
# ---------------------------------------------------------------------------


def test_every_module_without_its_own_page_is_reachable_when_earned(client, admin):
    """No module can be declared and then be unreachable.

    Scoped by `url_name` rather than by `access`, which is what the
    narrower version of this test missed: Messages is available to every
    client *and* has no page of its own, so it fell through the gap and
    404'd for everybody.
    """
    _org, user = _client_with(
        admin,
        categories=["search", "paid", "social", "email", "analytics"],
    )
    sign_in(client, user)

    for module in PORTAL_MODULES:
        if module.url_name or module.key == "strategy":
            continue
        assert client.get(portal_url(module.key)).status_code == 200, module.key


def test_every_module_declares_how_it_is_unlocked():
    for module in PORTAL_MODULES:
        assert module.access in {ALWAYS, ANY_SERVICE, SERVICE}, module.key


def test_a_dedicated_route_actually_exists():
    """Checked on `url_name`, not on `built`.

    They are different questions: Campaigns shows real records through
    the shared area route and has no page of its own. Conflating the two
    once left it labelled "soon" while it was already serving live data.
    """
    from django.urls import NoReverseMatch
    from django.urls import reverse as resolve

    for module in PORTAL_MODULES:
        if not module.url_name:
            continue
        try:
            resolve(module.url_name)
        except NoReverseMatch:  # pragma: no cover - a typo in the registry
            pytest.fail(f"{module.key} points at a route that does not exist")


def test_a_module_with_no_page_of_its_own_says_what_it_will_hold():
    """So the shared area page explains itself instead of apologising."""
    for module in PORTAL_MODULES:
        if module.url_name:
            continue
        assert module.will_show, module.key


# ---------------------------------------------------------------------------
# Onboarding rather than fake data
# ---------------------------------------------------------------------------


def test_a_client_with_nothing_gets_onboarding_not_a_dashboard_of_zeroes(client, admin):
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)
    sign_in(client, user)

    body = client.get(reverse("organizations:overview")).content

    assert b"Your workspace is ready" in body
    assert b"Browse services" in body
    assert b"Active services" not in body, "no empty metric tiles"


def test_a_client_with_services_gets_the_dashboard(client, admin):
    _org, user = _client_with(admin, categories=["search"])
    sign_in(client, user)

    body = client.get(reverse("organizations:overview")).content

    assert b"Active projects &amp; services" in body
    assert b"Your next step" in body
    assert b"Your workspace is ready" not in body


def test_the_module_page_says_what_opened_it(client, admin):
    _org, user = _client_with(admin, categories=["search"])
    sign_in(client, user)

    body = client.get(portal_url("seo")).content

    assert b"Why you can see this" in body
    assert b"What you will find here" in body


def test_the_module_page_invents_no_data(client, admin):
    """A plausible figure now is a figure nobody trusts later."""
    import re

    _org, user = _client_with(admin, categories=["paid"])
    sign_in(client, user)

    body = client.get(portal_url("paid_ads")).content.decode()
    # Whitespace collapsed before anything is asserted about prose: a
    # template wraps where it wraps, and a test that depends on which
    # word a line break lands between fails on an unrelated reflow.
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))

    # Asserted on the promise rather than one phrasing of it: the page
    # now says either "we are still building this area" or "nothing
    # running here yet" depending on whether campaigns exist, and both
    # branches make the same commitment.
    assert "until it is real" in text
    # No currency amounts or percentages anywhere in the content area.
    assert not re.search(r"\$\s?\d|\d+%", text), "the page shows a number"
