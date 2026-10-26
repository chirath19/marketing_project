"""Organization A cannot reach Organization B's services.

This is the guarantee the whole platform rests on, and a subscription is
the record that makes it concrete: it is what a client is paying for,
what they are owed, and what opens their workspace. A leak here is a leak
of commercial terms between companies that may well be competitors.

So the rule is tested at every layer it could be broken at — the
queryset, the selector, the client's own pages and the staff pages —
rather than once at the top and trusted the rest of the way down.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_member, make_org
from apps.staff.tests.factories import (
    PASSWORD,
    assign_client,
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
def two_clients():
    """Two unrelated clients, each paying for a different service.

    Returns ``((org_a, user_a, sub_a), (org_b, user_b, sub_b))``.
    """
    admin = make_super_admin_user("setup@heliograph.agency")

    org_a, org_b = make_org("Vantage Interiors"), make_org("Northwind Supply")
    user_a = make_user(email="a@vantage.example")
    user_b = make_user(email="b@northwind.example")
    make_member(org_a, user_a)
    make_member(org_b, user_b)

    seo = make_service("SEO growth retainer", category_slug="search",
                       workspace_module="seo")
    ads = make_service("Google Ads management", category_slug="paid",
                       workspace_module="paid_ads", slug="google-ads")

    sub_a = make_subscription(org_a, service=seo, actor=admin)
    sub_b = make_subscription(org_b, service=ads, actor=admin)

    return (org_a, user_a, sub_a), (org_b, user_b, sub_b)


# ---------------------------------------------------------------------------
# The queryset itself
# ---------------------------------------------------------------------------


def test_the_queryset_shows_a_client_only_their_own(two_clients):
    (_org_a, user_a, sub_a), (_org_b, _user_b, sub_b) = two_clients

    visible = set(
        ClientSubscription.objects.visible_to(user_a).values_list("pk", flat=True)
    )

    assert visible == {sub_a.pk}
    assert sub_b.pk not in visible


def test_the_selector_shows_a_client_only_their_own(two_clients):
    (_org_a, user_a, sub_a), (_org_b, _user_b, sub_b) = two_clients

    visible = set(
        selectors.subscriptions_for_client(user_a).values_list("pk", flat=True)
    )

    assert visible == {sub_a.pk}
    assert sub_b.pk not in visible


def test_an_anonymous_visitor_sees_nothing(two_clients):
    from django.contrib.auth.models import AnonymousUser

    assert not ClientSubscription.objects.visible_to(AnonymousUser()).exists()


def test_a_removed_member_stops_seeing_the_services(two_clients):
    """Isolation follows active membership, not a past association."""
    from apps.organizations.models import MemberStatus, OrganizationMember

    (org_a, user_a, sub_a), _b = two_clients
    assert sub_a.pk in set(
        selectors.subscriptions_for_client(user_a).values_list("pk", flat=True))

    OrganizationMember.objects.filter(organization=org_a, user=user_a).update(
        status=MemberStatus.REMOVED)

    assert not selectors.subscriptions_for_client(user_a).exists()


# ---------------------------------------------------------------------------
# Through the client's own pages
# ---------------------------------------------------------------------------


def test_a_clients_service_list_never_names_another_client(client, two_clients):
    (_org_a, user_a, sub_a), (_org_b, _user_b, sub_b) = two_clients
    sign_in(client, user_a)

    body = client.get(reverse("organizations:services")).content

    assert sub_a.name.encode() in body
    assert sub_b.name.encode() not in body
    assert b"Northwind" not in body


def test_another_clients_service_is_a_404_not_a_403(client, two_clients):
    """Confirming it exists is itself information they should not get."""
    (_org_a, user_a, _sub_a), (_org_b, _user_b, sub_b) = two_clients
    sign_in(client, user_a)

    response = client.get(reverse("organizations:service_detail", args=[sub_b.pk]))

    assert response.status_code == 404


def test_a_signed_out_visitor_is_sent_to_sign_in(client, two_clients):
    (_org_a, _user_a, sub_a), _b = two_clients

    response = client.get(reverse("organizations:service_detail", args=[sub_a.pk]))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_a_clients_unlocked_modules_come_only_from_their_own_services(two_clients):
    """Org B pays for ads; that must not open the ads area for org A."""
    (_org_a, user_a, _sub_a), (_org_b, user_b, _sub_b) = two_clients

    keys_a = {module.key for module in selectors.unlocked_modules(user_a)}
    keys_b = {module.key for module in selectors.unlocked_modules(user_b)}

    assert keys_a == {"seo"}
    assert keys_b == {"paid_ads"}


# ---------------------------------------------------------------------------
# Through the staff pages
# ---------------------------------------------------------------------------


def test_staff_assigned_to_one_client_cannot_see_the_others_services(two_clients):
    (org_a, _user_a, sub_a), (_org_b, _user_b, sub_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Subs", ["subscriptions_view", "organizations_view"])],
    )
    assign_client(staff, org_a)

    visible = set(
        selectors.visible_subscriptions(staff.user).values_list("pk", flat=True)
    )

    assert visible == {sub_a.pk}
    assert sub_b.pk not in visible


def test_staff_assigned_elsewhere_get_a_404_on_the_detail_page(client, two_clients):
    (org_a, _user_a, _sub_a), (_org_b, _user_b, sub_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Subs", ["subscriptions_view", "organizations_view"])],
    )
    assign_client(staff, org_a)
    sign_in(client, staff.user)

    response = client.get(reverse("staff:subscription_detail", args=[sub_b.pk]))

    assert response.status_code == 404


def test_staff_assigned_elsewhere_cannot_change_a_status(two_clients):
    """The service layer refuses, not just the view.

    Checked here because the view is one caller of many: the quote path,
    a management command and anything written later all go through the
    same function, and the rule has to live where they all meet it.
    """
    (org_a, _user_a, _sub_a), (_org_b, _user_b, sub_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Subs", ["subscriptions_view", "subscriptions_approve"])],
    )
    assign_client(staff, org_a)

    with pytest.raises(PermissionDenied):
        services.change_status(subscription=sub_b,
                               status=SubscriptionStatus.PAUSED,
                               actor=staff.user)

    sub_b.refresh_from_db()
    assert sub_b.status == SubscriptionStatus.ACTIVE


def test_staff_assigned_elsewhere_cannot_add_a_service(two_clients):
    (org_a, _user_a, _sub_a), (org_b, _user_b, _sub_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Subs", ["subscriptions_view", "subscriptions_create"])],
    )
    assign_client(staff, org_a)
    service = make_service("Local search", category_slug="search", slug="local")

    with pytest.raises(PermissionDenied):
        services.create_subscription(organization=org_b, service=service,
                                     actor=staff.user)

    assert not ClientSubscription.objects.filter(organization=org_b,
                                                 service=service).exists()


def test_a_client_user_is_refused_the_staff_pages(client, two_clients):
    (_org_a, user_a, sub_a), _b = two_clients
    sign_in(client, user_a)

    assert client.get(reverse("staff:module_subscriptions")).status_code == 403
    assert client.get(
        reverse("staff:subscription_detail", args=[sub_a.pk])).status_code == 403


def test_staff_without_the_permission_are_refused(client, two_clients):
    nobody = make_staff_member("nobody@heliograph.agency")
    sign_in(client, nobody.user)

    assert client.get(reverse("staff:module_subscriptions")).status_code == 403


def test_a_super_admin_sees_every_clients_services(two_clients):
    (_org_a, _user_a, sub_a), (_org_b, _user_b, sub_b) = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    visible = set(
        selectors.visible_subscriptions(admin).values_list("pk", flat=True)
    )

    assert {sub_a.pk, sub_b.pk} <= visible


# ---------------------------------------------------------------------------
# Internal notes
# ---------------------------------------------------------------------------


def test_internal_notes_never_reach_the_client(client, two_clients):
    (_org_a, user_a, sub_a), _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    services.add_note(subscription=sub_a, actor=admin,
                      body="Margin is thin, review at renewal.")
    sign_in(client, user_a)

    body = client.get(reverse("organizations:service_detail",
                              args=[sub_a.pk])).content

    assert b"Margin is thin" not in body


def test_internal_notes_on_the_record_never_reach_the_client(client, two_clients):
    """The field, not just the history entry."""
    (_org_a, user_a, sub_a), _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    services.update_subscription(subscription=sub_a, actor=admin,
                                 internal_notes="Chasing unpaid invoice.")
    sign_in(client, user_a)

    body = client.get(reverse("organizations:service_detail",
                              args=[sub_a.pk])).content

    assert b"unpaid invoice" not in body


def test_a_note_can_be_shared_deliberately(client, two_clients):
    (_org_a, user_a, sub_a), _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    services.add_note(subscription=sub_a, actor=admin, is_internal=False,
                      body="Your October report is published.")
    sign_in(client, user_a)

    body = client.get(reverse("organizations:service_detail",
                              args=[sub_a.pk])).content

    assert b"October report is published" in body


def test_a_client_is_only_notified_about_their_own_services(two_clients):
    from apps.notifications.models import Notification

    (_org_a, user_a, _sub_a), (org_b, user_b, _sub_b) = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    service = make_service("Local search", category_slug="search", slug="local")
    subscription = make_subscription(org_b, service=service, actor=admin,
                                     status=SubscriptionStatus.ACTIVE)

    # Scoped to this service's own notification. Both clients already
    # have one about their own retainer, from the fixture, so a blanket
    # check would pass for the wrong reason.
    recipients = set(
        Notification.objects.filter(category="subscription",
                                    title__startswith=subscription.name)
        .values_list("recipient__email", flat=True)
    )

    assert recipients == {user_b.email}
    assert user_a.email not in recipients
