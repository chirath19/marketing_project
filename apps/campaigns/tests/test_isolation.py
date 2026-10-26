"""Organization A cannot reach Organization B's campaigns.

A campaign carries a client's budget, their objectives and the agency's
notes about their account. A leak here is a leak between companies that
may well be competitors, so the rule is tested at every layer it could
be broken at — the queryset, the selector, the client's pages and the
staff pages — rather than once at the top and trusted the rest of the
way down.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.campaigns import selectors, services
from apps.campaigns.models import Campaign, CampaignStatus
from apps.campaigns.tests.factories import make_campaign
from apps.organizations.tests.factories import make_member, make_org
from apps.staff.tests.factories import (
    PASSWORD,
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def two_clients():
    """Two unrelated clients, each with a campaign.

    Returns ``((org_a, user_a, campaign_a), (org_b, user_b, campaign_b))``.
    """
    admin = make_super_admin_user("setup@heliograph.agency")

    org_a, org_b = make_org("Vantage Interiors"), make_org("Northwind Supply")
    user_a = make_user(email="a@vantage.example")
    user_b = make_user(email="b@northwind.example")
    make_member(org_a, user_a)
    make_member(org_b, user_b)

    campaign_a = make_campaign(org_a, actor=admin, name="Vantage spring push",
                               service_type="seo")
    campaign_b = make_campaign(org_b, actor=admin, name="Northwind lead gen",
                               service_type="paid_ads")

    return (org_a, user_a, campaign_a), (org_b, user_b, campaign_b)


# ---------------------------------------------------------------------------
# The queryset itself
# ---------------------------------------------------------------------------


def test_the_queryset_shows_a_client_only_their_own(two_clients):
    (_org_a, user_a, campaign_a), (_org_b, _user_b, campaign_b) = two_clients

    visible = set(Campaign.objects.visible_to(user_a).values_list("pk", flat=True))

    assert visible == {campaign_a.pk}
    assert campaign_b.pk not in visible


def test_the_selector_shows_a_client_only_their_own(two_clients):
    (_org_a, user_a, campaign_a), (_org_b, _user_b, campaign_b) = two_clients

    visible = set(
        selectors.campaigns_for_client(user_a).values_list("pk", flat=True)
    )

    assert visible == {campaign_a.pk}
    assert campaign_b.pk not in visible


def test_filtering_by_service_type_does_not_widen_the_scope(two_clients):
    """Org B's campaign is `paid_ads`. Asking org A for paid campaigns
    must not reach it."""
    (_org_a, user_a, _campaign_a), (_org_b, _user_b, campaign_b) = two_clients

    found = set(
        selectors.campaigns_for_client(user_a, service_type="paid_ads")
        .values_list("pk", flat=True)
    )

    assert campaign_b.pk not in found
    assert found == set()


def test_an_anonymous_visitor_sees_nothing(two_clients):
    from django.contrib.auth.models import AnonymousUser

    assert not Campaign.objects.visible_to(AnonymousUser()).exists()


def test_a_removed_member_stops_seeing_the_campaigns(two_clients):
    """Isolation follows active membership, not a past association."""
    from apps.organizations.models import MemberStatus, OrganizationMember

    (org_a, user_a, _campaign_a), _b = two_clients
    assert selectors.campaigns_for_client(user_a).exists()

    OrganizationMember.objects.filter(organization=org_a, user=user_a).update(
        status=MemberStatus.REMOVED)

    assert not selectors.campaigns_for_client(user_a).exists()


# ---------------------------------------------------------------------------
# Through the client's own pages
# ---------------------------------------------------------------------------


def test_another_clients_campaign_is_a_404_not_a_403(client, two_clients):
    """Confirming it exists is itself information they should not get."""
    (_org_a, user_a, _campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    sign_in(client, user_a)

    response = client.get(
        reverse("organizations:campaign_detail", args=[campaign_b.pk]))

    assert response.status_code == 404


def test_a_signed_out_visitor_is_sent_to_sign_in(client, two_clients):
    (_org_a, _user_a, campaign_a), _b = two_clients

    response = client.get(
        reverse("organizations:campaign_detail", args=[campaign_a.pk]))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_the_campaigns_area_never_names_another_client(client, two_clients):
    """Needs an active service to open the area at all."""
    from apps.subscriptions.models import SubscriptionStatus
    from apps.subscriptions.tests.factories import make_service, make_subscription

    (org_a, user_a, campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")
    make_subscription(org_a, actor=admin,
                      service=make_service("SEO", category_slug="search"),
                      status=SubscriptionStatus.ACTIVE)
    sign_in(client, user_a)

    body = client.get(
        reverse("organizations:portal_module", args=["campaigns"])).content

    assert campaign_a.name.encode() in body
    assert campaign_b.name.encode() not in body
    assert b"Northwind" not in body


# ---------------------------------------------------------------------------
# Through the staff pages
# ---------------------------------------------------------------------------


def test_staff_assigned_to_one_client_cannot_see_the_others_campaigns(two_clients):
    (org_a, _user_a, campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "organizations_view"])],
    )
    assign_client(staff, org_a)

    visible = set(
        selectors.visible_campaigns(staff.user).values_list("pk", flat=True)
    )

    assert visible == {campaign_a.pk}
    assert campaign_b.pk not in visible


def test_staff_assigned_elsewhere_get_a_404_on_the_detail_page(client, two_clients):
    (org_a, _user_a, _campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "organizations_view"])],
    )
    assign_client(staff, org_a)
    sign_in(client, staff.user)

    response = client.get(reverse("staff:campaign_detail", args=[campaign_b.pk]))

    assert response.status_code == 404


def test_staff_assigned_elsewhere_cannot_change_a_status(two_clients):
    """The service layer refuses, not just the view.

    Checked here because the view is one caller of many: a future SEO
    module, an API and a management command all go through the same
    function, and the rule has to live where they all meet it.
    """
    (org_a, _user_a, _campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "campaigns_approve"])],
    )
    assign_client(staff, org_a)

    with pytest.raises(PermissionDenied):
        services.change_status(campaign=campaign_b, status=CampaignStatus.LIVE,
                               actor=staff.user)

    campaign_b.refresh_from_db()
    assert campaign_b.status == CampaignStatus.PLANNED


def test_staff_assigned_elsewhere_cannot_create_a_campaign(two_clients):
    (org_a, _user_a, _campaign_a), (org_b, _user_b, _campaign_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "campaigns_create"])],
    )
    assign_client(staff, org_a)

    with pytest.raises(PermissionDenied):
        services.create_campaign(organization=org_b, name="Sneaky",
                                 actor=staff.user, service_type="seo")

    assert not Campaign.objects.filter(organization=org_b, name="Sneaky").exists()


def test_staff_assigned_elsewhere_cannot_write_a_note(two_clients):
    (org_a, _user_a, _campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "campaigns_edit"])],
    )
    assign_client(staff, org_a)

    with pytest.raises(PermissionDenied):
        services.add_note(campaign=campaign_b, body="Prying.", actor=staff.user)


def test_a_client_user_is_refused_the_staff_pages(client, two_clients):
    (_org_a, user_a, campaign_a), _b = two_clients
    sign_in(client, user_a)

    assert client.get(reverse("staff:module_campaigns")).status_code == 403
    assert client.get(
        reverse("staff:campaign_detail", args=[campaign_a.pk])).status_code == 403


def test_staff_without_the_permission_are_refused(client, two_clients):
    nobody = make_staff_member("nobody@heliograph.agency")
    sign_in(client, nobody.user)

    assert client.get(reverse("staff:module_campaigns")).status_code == 403


def test_a_super_admin_sees_every_clients_campaigns(two_clients):
    (_org_a, _user_a, campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    visible = set(
        selectors.visible_campaigns(admin).values_list("pk", flat=True)
    )

    assert {campaign_a.pk, campaign_b.pk} <= visible


def test_search_never_crosses_the_boundary(two_clients):
    """A search box is a classic way round a scoped list."""
    (org_a, _user_a, _campaign_a), (_org_b, _user_b, campaign_b) = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "organizations_view"])],
    )
    assign_client(staff, org_a)

    found = set(
        selectors.visible_campaigns(staff.user, search="Northwind")
        .values_list("pk", flat=True)
    )

    assert campaign_b.pk not in found
    assert found == set()


# ---------------------------------------------------------------------------
# Internal notes
# ---------------------------------------------------------------------------


def test_internal_notes_never_reach_the_client(client, two_clients):
    (_org_a, user_a, campaign_a), _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    services.add_note(campaign=campaign_a, actor=admin,
                      body="Client is slow to approve creative.")
    sign_in(client, user_a)

    body = client.get(
        reverse("organizations:campaign_detail", args=[campaign_a.pk])).content

    assert b"slow to approve" not in body


def test_the_internal_notes_field_never_reaches_the_client(client, two_clients):
    """The field, not just the history entry."""
    (_org_a, user_a, campaign_a), _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    services.update_campaign(campaign=campaign_a, actor=admin,
                             internal_notes="Margin is thin on this account.")
    sign_in(client, user_a)

    body = client.get(
        reverse("organizations:campaign_detail", args=[campaign_a.pk])).content

    assert b"Margin is thin" not in body


def test_the_internal_description_never_reaches_the_client(client, two_clients):
    (_org_a, user_a, campaign_a), _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    services.update_campaign(campaign=campaign_a, actor=admin,
                             description="Internal rationale, staff only.")
    sign_in(client, user_a)

    body = client.get(
        reverse("organizations:campaign_detail", args=[campaign_a.pk])).content

    assert b"Internal rationale" not in body


def test_a_note_can_be_shared_deliberately(client, two_clients):
    (_org_a, user_a, campaign_a), _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    services.add_note(campaign=campaign_a, actor=admin, is_internal=False,
                      body="New creative goes live on Monday.")
    sign_in(client, user_a)

    body = client.get(
        reverse("organizations:campaign_detail", args=[campaign_a.pk])).content

    assert b"New creative goes live" in body


def test_a_client_is_only_notified_about_their_own_campaigns(two_clients):
    from apps.notifications.models import Notification

    (_org_a, user_a, _campaign_a), (org_b, user_b, _campaign_b) = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    campaign = make_campaign(org_b, actor=admin, name="Northwind autumn",
                             status=CampaignStatus.LIVE)

    recipients = set(
        Notification.objects.filter(category="campaign",
                                    title__startswith=campaign.name)
        .values_list("recipient__email", flat=True)
    )

    assert recipients == {user_b.email}
    assert user_a.email not in recipients
