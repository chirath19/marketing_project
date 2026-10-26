"""The client service lifecycle.

Isolation has its own module. This one is about the workflow: that a
service can be attached by hand or from an accepted quote, that its
status machine refuses moves it should refuse, and — the point of the
whole phase — that **what a client sees in their workspace is a function
of their active services and nothing else**.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_member, make_org
from apps.staff.tests.factories import (
    PASSWORD,
    make_role,
    make_staff_member,
    make_super_admin_user,
)
from apps.subscriptions import selectors, services
from apps.subscriptions.models import ClientSubscription, SubscriptionStatus
from apps.subscriptions.tests.factories import make_service, make_subscription

pytestmark = pytest.mark.django_db


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def admin():
    return make_super_admin_user("boss@heliograph.agency")


@pytest.fixture
def tenant():
    """A client organization with one person in it."""
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)
    return org, user


# ---------------------------------------------------------------------------
# Attaching a service by hand
# ---------------------------------------------------------------------------


def test_a_service_can_be_attached_to_a_client(admin, tenant):
    org, _user = tenant
    service = make_service("SEO retainer", price="2400")

    subscription = services.create_subscription(
        organization=org, service=service, actor=admin,
    )

    assert subscription.organization == org
    assert subscription.status == SubscriptionStatus.PENDING
    assert subscription.created_by == admin


def test_pricing_is_copied_from_the_catalogue_not_referenced(admin, tenant):
    """A later catalogue change must not alter what a client is paying."""
    org, _user = tenant
    service = make_service("SEO retainer", price="2400")
    subscription = services.create_subscription(
        organization=org, service=service, actor=admin,
    )

    service.price = Decimal("9999")
    service.save(update_fields=["price"])
    subscription.refresh_from_db()

    assert subscription.price == Decimal("2400")


def test_a_client_can_hold_several_services_at_once(admin, tenant):
    org, _user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    ads = make_service("Google Ads", category_slug="paid",
                       workspace_module="paid_ads")

    services.create_subscription(organization=org, service=seo, actor=admin)
    services.create_subscription(organization=org, service=ads, actor=admin)

    assert ClientSubscription.objects.filter(organization=org).count() == 2


def test_the_same_service_cannot_be_open_twice_for_one_client(admin, tenant):
    """A double-charge waiting to happen, and it makes "is this client
    getting SEO?" ambiguous."""
    org, _user = tenant
    service = make_service("SEO retainer")
    services.create_subscription(organization=org, service=service, actor=admin)

    with pytest.raises(ValidationError):
        services.create_subscription(organization=org, service=service,
                                     actor=admin)


def test_the_same_service_can_be_sold_again_after_the_first_one_closed(admin, tenant):
    """Clients come back. The constraint is about overlap, not history."""
    org, _user = tenant
    service = make_service("SEO retainer")
    first = services.create_subscription(organization=org, service=service,
                                         actor=admin)
    services.change_status(subscription=first,
                           status=SubscriptionStatus.CANCELLED, actor=admin)

    second = services.create_subscription(organization=org, service=service,
                                          actor=admin)

    assert second.pk != first.pk


def test_a_service_cannot_end_before_it_starts(admin, tenant):
    org, _user = tenant
    today = timezone.localdate()

    with pytest.raises(ValidationError):
        services.create_subscription(
            organization=org, service=make_service(), actor=admin,
            starts_on=today, ends_on=today - timedelta(days=1),
        )


def test_creating_a_service_does_not_email_anybody(admin, tenant):
    org, _user = tenant
    services.create_subscription(organization=org, service=make_service(),
                                 actor=admin, status=SubscriptionStatus.ACTIVE)

    assert mail.outbox == []


def test_activating_tells_the_clients_own_people_in_app(admin, tenant):
    from apps.notifications.models import Notification

    org, user = tenant
    subscription = make_subscription(org, actor=admin,
                                     status=SubscriptionStatus.PENDING)
    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.ACTIVE, actor=admin)

    assert Notification.objects.filter(
        recipient=user, category="subscription",
        title__contains=subscription.name).exists()


# ---------------------------------------------------------------------------
# The lifecycle
# ---------------------------------------------------------------------------


def test_a_service_moves_through_its_lifecycle(admin, tenant):
    org, _user = tenant
    subscription = make_subscription(org, actor=admin,
                                     status=SubscriptionStatus.PENDING)

    for status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED,
                   SubscriptionStatus.ACTIVE, SubscriptionStatus.COMPLETED):
        services.change_status(subscription=subscription, status=status,
                               actor=admin)

    subscription.refresh_from_db()
    assert subscription.status == SubscriptionStatus.COMPLETED
    assert subscription.ended_at is not None


def test_activating_stamps_the_start_date_if_there_is_none(admin, tenant):
    org, _user = tenant
    subscription = make_subscription(org, actor=admin,
                                     status=SubscriptionStatus.PENDING)
    assert subscription.starts_on is None

    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.ACTIVE, actor=admin)

    subscription.refresh_from_db()
    assert subscription.starts_on == timezone.localdate()


def test_a_cancelled_service_is_a_dead_end(admin, tenant):
    """Reviving it should be a new agreement, not a dropdown."""
    org, _user = tenant
    subscription = make_subscription(org, actor=admin)
    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.CANCELLED, actor=admin)

    with pytest.raises(ValidationError):
        services.change_status(subscription=subscription,
                               status=SubscriptionStatus.ACTIVE, actor=admin)


def test_a_completed_service_can_be_picked_back_up(admin, tenant):
    """Clients renew, and a renewal re-keyed as a new row loses the
    history of the first engagement."""
    org, _user = tenant
    subscription = make_subscription(org, actor=admin)
    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.COMPLETED, actor=admin)

    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.ACTIVE, actor=admin)

    subscription.refresh_from_db()
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.ended_at is None, "it is live again"


def test_an_impossible_move_is_refused(admin, tenant):
    org, _user = tenant
    subscription = make_subscription(org, actor=admin,
                                     status=SubscriptionStatus.PENDING)

    with pytest.raises(ValidationError):
        services.change_status(subscription=subscription,
                               status=SubscriptionStatus.COMPLETED, actor=admin)


def test_changing_status_needs_its_own_right(tenant):
    """Pausing a client's advertising stops work and stops billing. That
    is not the same decision as editing a note."""
    org, _user = tenant
    admin = make_super_admin_user("setup@heliograph.agency")
    subscription = make_subscription(org, actor=admin)

    editor = make_staff_member(
        "editor@heliograph.agency",
        roles=[make_role("Editor", ["subscriptions_view", "subscriptions_edit"])],
    )

    with pytest.raises(PermissionDenied):
        services.change_status(subscription=subscription,
                               status=SubscriptionStatus.PAUSED,
                               actor=editor.user)


def test_every_change_lands_in_the_history(admin, tenant):
    org, _user = tenant
    subscription = make_subscription(org, actor=admin,
                                     status=SubscriptionStatus.PENDING)
    before = subscription.events.count()

    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.ACTIVE, actor=admin)
    services.update_subscription(subscription=subscription, actor=admin,
                                 price=Decimal("3000"))

    assert subscription.events.count() == before + 2


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


def test_a_service_past_its_end_date_is_flagged(admin, tenant):
    org, _user = tenant
    subscription = make_subscription(
        org, actor=admin, ends_on=timezone.localdate() - timedelta(days=1),
    )

    assert subscription.is_past_end


def test_expiring_due_services_records_why(admin, tenant):
    org, _user = tenant
    subscription = make_subscription(
        org, actor=admin, ends_on=timezone.localdate() - timedelta(days=2),
    )

    expired = services.expire_due(actor=admin)

    subscription.refresh_from_db()
    assert subscription in expired
    assert subscription.status == SubscriptionStatus.EXPIRED
    assert subscription.events.filter(body__contains="Expired").exists()


def test_a_service_with_no_end_date_never_expires(admin, tenant):
    org, _user = tenant
    subscription = make_subscription(org, actor=admin, ends_on=None)

    services.expire_due(actor=admin)

    subscription.refresh_from_db()
    assert subscription.status == SubscriptionStatus.ACTIVE


def test_expiring_soon_finds_the_ones_about_to_lapse(admin, tenant):
    org, _user = tenant
    soon = make_subscription(
        org, actor=admin, ends_on=timezone.localdate() + timedelta(days=10),
    )
    make_subscription(
        org, actor=admin, service=make_service("Ads", category_slug="paid"),
        ends_on=timezone.localdate() + timedelta(days=200),
    )

    found = list(selectors.expiring_soon(admin))

    assert found == [soon]


# ---------------------------------------------------------------------------
# One workspace, decided by data
# ---------------------------------------------------------------------------


def test_an_active_service_opens_its_workspace_area(admin, tenant):
    org, user = tenant
    assert selectors.unlocked_modules(user) == []

    subscription = make_subscription(org, actor=admin,
                                     status=SubscriptionStatus.PENDING)
    assert selectors.unlocked_modules(user) == [], "pending opens nothing"

    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.ACTIVE, actor=admin)

    assert [module.key for module in selectors.unlocked_modules(user)] == ["seo"]


def test_pausing_a_service_closes_its_area_again(admin, tenant):
    """A paused retainer should not keep a live performance area open."""
    org, user = tenant
    subscription = make_subscription(org, actor=admin)
    assert selectors.unlocked_modules(user)

    services.change_status(subscription=subscription,
                           status=SubscriptionStatus.PAUSED, actor=admin)

    assert selectors.unlocked_modules(user) == []


def test_several_services_open_several_areas(admin, tenant):
    org, user = tenant
    make_subscription(org, actor=admin,
                      service=make_service("SEO", category_slug="search"))
    make_subscription(org, actor=admin,
                      service=make_service("Ads", category_slug="paid",
                                           workspace_module="paid_ads"))

    keys = {module.key for module in selectors.unlocked_modules(user)}

    assert keys == {"seo", "paid_ads"}


def test_two_services_in_one_category_open_that_area_once(admin, tenant):
    org, user = tenant
    make_subscription(org, actor=admin,
                      service=make_service("Technical SEO", category_slug="search"))
    make_subscription(org, actor=admin,
                      service=make_service("Local SEO", category_slug="search"))

    modules = selectors.unlocked_modules(user)

    assert [module.key for module in modules] == ["seo"]


def test_a_category_with_no_module_opens_nothing(admin, tenant):
    """A service can be sold without a dashboard behind it."""
    org, user = tenant
    make_subscription(org, actor=admin, service=make_service(
        "Consulting day", category_slug="advisory", workspace_module=""))

    assert selectors.unlocked_modules(user) == []


def test_the_workspace_keeps_specialist_details_inside_the_project(client, admin, tenant):
    org, user = tenant
    subscription = make_subscription(org, actor=admin)
    sign_in(client, user)
    body = client.get(reverse("organizations:services")).content
    assert b"Projects &amp; services" in body
    assert reverse("organizations:service_detail", args=[subscription.pk]).encode() in body
    detail = client.get(reverse("organizations:service_detail", args=[subscription.pk])).content
    assert b"Work details" in detail
    assert b'href="/organization/area/seo/"' in detail


# ---------------------------------------------------------------------------
# From an accepted quote
# ---------------------------------------------------------------------------


def _accepted_quote(org, admin, *, services_on_it):  # noqa: ANN001, ANN202
    """A quote, accepted, attached to this client.

    Accepted by writing the status directly, so these tests exercise the
    manual conversion on its own; acceptance through the workflow already
    activates the services (see the tests after these).
    """
    from apps.leads import quote_services
    from apps.leads.models import QuoteStatus
    from apps.leads.tests.factories import make_quote_request

    quote = make_quote_request(services=[s.name for s in services_on_it])
    quote_services.attach_to_organization(quote=quote, organization=org,
                                          actor=admin)

    # Point each line at a real catalogue entry, as the live quote
    # builder does.
    for item, service in zip(quote.items.all(), services_on_it, strict=True):
        item.service = service
        item.quoted_amount = service.price
        item.currency = service.currency
        item.billing_type = service.billing_type
        item.save()

    for status in (QuoteStatus.REVIEWING, QuoteStatus.PROPOSAL_READY):
        quote_services.change_status(quote=quote, status=status, actor=admin)
    quote.status = QuoteStatus.ACCEPTED
    quote.save(update_fields=["status"])

    return quote


def _proposed_quote(org, admin, *, services_on_it, submitted_by=None):  # noqa: ANN001, ANN202
    """A priced quote waiting on the client's decision."""
    from apps.leads import quote_services
    from apps.leads.models import QuoteStatus
    from apps.leads.tests.factories import make_quote_request

    quote = make_quote_request(services=[s.name for s in services_on_it],
                               submitted_by=submitted_by)
    if org is not None:
        quote_services.attach_to_organization(quote=quote, organization=org, actor=admin)
    for item, service in zip(quote.items.all(), services_on_it, strict=True):
        item.service, item.quoted_amount = service, service.price
        item.currency, item.billing_type = service.currency, service.billing_type
        item.save()
    for status in (QuoteStatus.REVIEWING, QuoteStatus.PROPOSAL_READY):
        quote_services.change_status(quote=quote, status=status, actor=admin)
    return quote


def test_a_client_accepting_activates_the_services_immediately(admin, tenant):
    from apps.leads import quote_services

    org, user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    quote = _proposed_quote(org, admin, services_on_it=[seo], submitted_by=user)

    quote_services.client_decision(quote=quote, accepted=True, actor=user)

    quote.refresh_from_db()
    service = ClientSubscription.objects.get(quote=quote)
    assert service.status == "active"
    assert service.activated_at is not None
    assert quote.is_active_work and quote.lifecycle_label == "Active"


def test_staff_recording_acceptance_also_activates(admin, tenant):
    from apps.leads import quote_services
    from apps.leads.models import QuoteStatus

    org, _user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    quote = _proposed_quote(org, admin, services_on_it=[seo])

    quote_services.change_status(quote=quote, status=QuoteStatus.ACCEPTED, actor=admin)

    assert ClientSubscription.objects.filter(quote=quote, status="active").count() == 1


def test_accepting_attaches_the_submitters_organization(admin, tenant):
    """A signed-in client's quote that lost its organization still goes live."""
    from apps.leads import quote_services

    org, user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    quote = _proposed_quote(None, admin, services_on_it=[seo], submitted_by=user)

    quote_services.client_decision(quote=quote, accepted=True, actor=user)

    quote.refresh_from_db()
    assert quote.organization == org
    assert ClientSubscription.objects.filter(quote=quote, status="active").exists()


def test_an_accepted_guest_quote_activates_once_a_client_is_attached(admin, tenant):
    from apps.leads import quote_services
    from apps.leads.models import QuoteActivity, QuoteStatus

    org, _user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    quote = _proposed_quote(None, admin, services_on_it=[seo])
    quote_services.change_status(quote=quote, status=QuoteStatus.ACCEPTED, actor=admin)
    assert not ClientSubscription.objects.filter(quote=quote).exists()
    assert QuoteActivity.objects.filter(quote=quote, is_internal=True,
                                        body__contains="Attach one").exists()

    quote_services.attach_to_organization(quote=quote, organization=org, actor=admin)

    assert ClientSubscription.objects.filter(quote=quote, status="active").exists()


def test_an_accepted_quote_becomes_the_services_it_agreed(admin, tenant):
    org, _user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    ads = make_service("Google Ads", category_slug="paid",
                       workspace_module="paid_ads")
    quote = _accepted_quote(org, admin, services_on_it=[seo, ads])

    created, skipped = services.create_from_quote(quote=quote, actor=admin)

    assert len(created) == 2
    assert skipped == []
    assert {s.service_id for s in created} == {seo.pk, ads.pk}
    assert all(s.quote_id == quote.pk for s in created)


def test_the_quoted_price_carries_onto_the_service(admin, tenant):
    org, _user = tenant
    seo = make_service("SEO retainer", category_slug="search", price="2400")
    quote = _accepted_quote(org, admin, services_on_it=[seo])
    quote.items.update(quoted_amount=Decimal("3100"))

    created, _skipped = services.create_from_quote(quote=quote, actor=admin)

    assert created[0].price == Decimal("3100"), "what was agreed, not the list price"


def test_a_line_dropped_from_scope_does_not_become_a_service(admin, tenant):
    org, _user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    ads = make_service("Google Ads", category_slug="paid",
                       workspace_module="paid_ads")
    quote = _accepted_quote(org, admin, services_on_it=[seo, ads])
    quote.items.filter(service=ads).update(is_included=False)

    created, _skipped = services.create_from_quote(quote=quote, actor=admin)

    assert [s.service_id for s in created] == [seo.pk]


def test_a_quote_that_is_not_accepted_becomes_nothing(admin, tenant):
    from apps.leads import quote_services
    from apps.leads.models import QuoteStatus
    from apps.leads.tests.factories import make_quote_request

    org, _user = tenant
    quote = make_quote_request()
    quote_services.attach_to_organization(quote=quote, organization=org,
                                          actor=admin)
    quote_services.change_status(quote=quote, status=QuoteStatus.REVIEWING,
                                 actor=admin)

    with pytest.raises(ValidationError):
        services.create_from_quote(quote=quote, actor=admin)


def test_a_quote_with_no_client_attached_is_refused(admin):
    """There is nobody to deliver to."""
    from apps.leads.models import QuoteStatus
    from apps.leads.tests.factories import make_quote_request

    quote = make_quote_request()
    quote.status = QuoteStatus.ACCEPTED
    quote.save(update_fields=["status"])

    with pytest.raises(ValidationError):
        services.create_from_quote(quote=quote, actor=admin)


def test_a_service_the_client_already_has_is_skipped_and_said_so(admin, tenant):
    """Silently dropping it is how a client ends up unknowingly unbilled."""
    org, _user = tenant
    seo = make_service("SEO retainer", category_slug="search")
    make_subscription(org, service=seo, actor=admin)
    quote = _accepted_quote(org, admin, services_on_it=[seo])

    created, skipped = services.create_from_quote(quote=quote, actor=admin)

    assert created == []
    assert len(skipped) == 1
    assert "already on their account" in skipped[0]


# ---------------------------------------------------------------------------
# Through the staff pages
# ---------------------------------------------------------------------------


def test_staff_can_attach_a_service_from_the_client_page(client, admin, tenant):
    org, _user = tenant
    service = make_service("SEO retainer")
    sign_in(client, admin)

    response = client.post(
        reverse("staff:subscription_create", args=[org.slug]),
        {"service": service.pk, "currency": "USD", "billing_type": "monthly"},
    )

    assert response.status_code == 302
    subscription = ClientSubscription.objects.get(organization=org)
    assert subscription.status == SubscriptionStatus.PENDING


def test_the_staff_list_shows_what_is_being_delivered(client, admin, tenant):
    org, _user = tenant
    subscription = make_subscription(org, actor=admin)
    sign_in(client, admin)

    body = client.get(reverse("staff:module_subscriptions")).content

    assert subscription.name.encode() in body
    assert org.label.encode() in body


def test_the_staff_detail_page_says_what_the_service_opens(client, admin, tenant):
    org, _user = tenant
    subscription = make_subscription(org, actor=admin)
    sign_in(client, admin)

    body = client.get(reverse("staff:subscription_detail",
                              args=[subscription.pk])).content

    assert b"What this opens" in body
    assert b"Open to them now" in body
