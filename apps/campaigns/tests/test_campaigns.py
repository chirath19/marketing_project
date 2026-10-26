"""The campaign engine.

Isolation has its own module. This one is about the engine itself: the
status machine, the staff workflow, and — the architectural point of the
phase — that every service area shares **one** campaign table rather than
growing a parallel one each.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import make_user
from apps.campaigns import registry, selectors, services
from apps.campaigns.models import Campaign, CampaignStatus
from apps.campaigns.tests.factories import make_campaign
from apps.organizations.tests.factories import make_member, make_org
from apps.staff.tests.factories import (
    PASSWORD,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def admin():
    return make_super_admin_user("boss@heliograph.agency")


@pytest.fixture
def tenant():
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)
    return org, user


# ---------------------------------------------------------------------------
# One engine, every service area
# ---------------------------------------------------------------------------


def test_every_service_area_uses_the_same_table(admin, tenant):
    """The architectural point: no parallel campaign models.

    Four service modules with four campaign tables would mean four status
    machines, four permission models and four isolation rules — and a
    combined view assembled from four queries that agree about nothing.
    """
    org, _user = tenant
    for key in ("seo", "paid_ads", "social", "email_marketing"):
        make_campaign(org, actor=admin, name=f"{key} work", service_type=key)

    assert Campaign.objects.filter(organization=org).count() == 4

    # And one query returns them all, which is what the supplied
    # dashboard shows.
    everything = selectors.visible_campaigns(admin)
    assert {c.service_type for c in everything} == {
        "seo", "paid_ads", "social", "email_marketing",
    }


def test_a_service_module_filters_the_shared_table(admin, tenant):
    """`of_type` is the hook a future SEO dashboard uses."""
    org, _user = tenant
    seo = make_campaign(org, actor=admin, name="Search work", service_type="seo")
    make_campaign(org, actor=admin, name="Ad work", service_type="paid_ads")

    found = selectors.visible_campaigns(admin, service_type="seo")

    assert [c.pk for c in found] == [seo.pk]


def test_an_unregistered_service_area_is_refused(admin, tenant):
    """A typo would otherwise create a campaign nothing can ever show."""
    org, _user = tenant

    with pytest.raises(ValidationError):
        services.create_campaign(organization=org, name="Nowhere",
                                 actor=admin, service_type="telepathy")


def test_the_objective_is_labelled_for_its_service_area(admin, tenant):
    """"Target positions" and "Cost per customer" are not the same
    question, and one generic label serves neither."""
    org, _user = tenant
    seo = make_campaign(org, actor=admin, service_type="seo")
    ads = make_campaign(org, actor=admin, name="Ads", service_type="paid_ads")

    assert seo.objective_label == "Target positions"
    assert ads.objective_label == "Cost per customer"


def test_every_registered_type_matches_a_portal_module():
    """A campaign type with no portal area would be invisible to the
    client who is paying for it."""
    from apps.core.modules import SERVICE_MODULES

    module_keys = {module.key for module in SERVICE_MODULES}
    for campaign_type in registry.all_types():
        assert campaign_type.key in module_keys, campaign_type.key


def test_a_type_with_no_detail_model_simply_has_none(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="seo")

    assert campaign.detail is None, "no detail model is registered yet"


def test_registering_a_type_is_idempotent(monkeypatch):
    """Modules are imported more than once in a test run."""
    monkeypatch.setattr(registry, "_TYPES", registry._TYPES.copy())
    before = len(registry.all_types())
    registry.register(registry.CampaignType(key="seo", label="Search"))

    assert len(registry.all_types()) == before


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


def test_a_campaign_starts_planned(admin, tenant):
    org, _user = tenant
    campaign = services.create_campaign(organization=org, name="Spring push",
                                        actor=admin, service_type="paid_ads")

    assert campaign.status == CampaignStatus.PLANNED
    assert campaign.started_at is None


def test_the_service_area_is_taken_from_the_service_when_not_given(admin, tenant):
    """So nobody has to remember the mapping."""
    from apps.subscriptions.models import SubscriptionStatus
    from apps.subscriptions.tests.factories import make_service, make_subscription

    org, _user = tenant
    subscription = make_subscription(
        org, actor=admin,
        service=make_service("Google Ads", category_slug="paid",
                             workspace_module="paid_ads"),
        status=SubscriptionStatus.ACTIVE,
    )

    campaign = services.create_campaign(
        organization=org, name="Q2 search", actor=admin,
        subscription=subscription,
    )

    assert campaign.service_type == "paid_ads"


def test_a_campaign_cannot_be_attached_to_another_clients_service(admin, tenant):
    """Otherwise one client's work lands on another client's invoice."""
    from apps.subscriptions.tests.factories import make_service, make_subscription

    org, _user = tenant
    other = make_org("Northwind Supply")
    theirs = make_subscription(other, actor=admin,
                               service=make_service("SEO", category_slug="search"))

    with pytest.raises(ValidationError):
        services.create_campaign(organization=org, name="Crossed wires",
                                 actor=admin, service_type="seo",
                                 subscription=theirs)


def test_a_campaign_cannot_end_before_it_starts(admin, tenant):
    org, _user = tenant
    today = timezone.localdate()

    with pytest.raises(ValidationError):
        services.create_campaign(
            organization=org, name="Backwards", actor=admin,
            service_type="seo", starts_on=today,
            ends_on=today - timedelta(days=1),
        )


def test_creating_a_campaign_does_not_email_anybody(admin, tenant):
    org, _user = tenant
    make_campaign(org, actor=admin, status=CampaignStatus.LIVE)

    assert mail.outbox == []


def test_taking_a_campaign_live_tells_the_client_in_app(admin, tenant):
    from apps.notifications.models import Notification

    org, user = tenant
    campaign = make_campaign(org, actor=admin)
    services.change_status(campaign=campaign, status=CampaignStatus.LIVE,
                           actor=admin)

    assert Notification.objects.filter(
        recipient=user, category="campaign",
        title__contains=campaign.name).exists()


# ---------------------------------------------------------------------------
# The status machine
# ---------------------------------------------------------------------------


def test_a_campaign_moves_through_its_lifecycle(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin)

    for status in (CampaignStatus.LIVE, CampaignStatus.PAUSED,
                   CampaignStatus.LIVE, CampaignStatus.DONE):
        services.change_status(campaign=campaign, status=status, actor=admin)

    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.DONE
    assert campaign.ended_at is not None


def test_going_live_stamps_the_start_date_if_there_is_none(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin)
    assert campaign.starts_on is None

    services.change_status(campaign=campaign, status=CampaignStatus.LIVE,
                           actor=admin)

    campaign.refresh_from_db()
    assert campaign.starts_on == timezone.localdate()
    assert campaign.started_at is not None


def test_a_cancelled_campaign_is_a_dead_end(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin)
    services.change_status(campaign=campaign, status=CampaignStatus.CANCELLED,
                           actor=admin)

    with pytest.raises(ValidationError):
        services.change_status(campaign=campaign, status=CampaignStatus.LIVE,
                               actor=admin)


def test_a_finished_campaign_can_run_again(admin, tenant):
    """A seasonal campaign that runs again next year is the same
    campaign, and re-keying it loses its history."""
    org, _user = tenant
    campaign = make_campaign(org, actor=admin, status=CampaignStatus.LIVE)
    services.change_status(campaign=campaign, status=CampaignStatus.DONE,
                           actor=admin)

    services.change_status(campaign=campaign, status=CampaignStatus.LIVE,
                           actor=admin)

    campaign.refresh_from_db()
    assert campaign.status == CampaignStatus.LIVE
    assert campaign.ended_at is None, "it is running again"


def test_an_impossible_move_is_refused(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin)

    with pytest.raises(ValidationError):
        services.change_status(campaign=campaign, status=CampaignStatus.DONE,
                               actor=admin)


def test_taking_a_campaign_live_needs_its_own_right(tenant):
    """Putting a client's advertising live commits their budget. That is
    not the same decision as correcting a description."""
    org, _user = tenant
    admin = make_super_admin_user("setup@heliograph.agency")
    campaign = make_campaign(org, actor=admin)

    editor = make_staff_member(
        "editor@heliograph.agency",
        roles=[make_role("Editor", ["campaigns_view", "campaigns_edit"])],
    )

    with pytest.raises(PermissionDenied):
        services.change_status(campaign=campaign, status=CampaignStatus.LIVE,
                               actor=editor.user)


def test_assigning_needs_its_own_right(tenant):
    org, _user = tenant
    admin = make_super_admin_user("setup@heliograph.agency")
    campaign = make_campaign(org, actor=admin)

    editor = make_staff_member(
        "editor@heliograph.agency",
        roles=[make_role("Editor", ["campaigns_view", "campaigns_edit"])],
    )

    with pytest.raises(PermissionDenied):
        services.assign(campaign=campaign, actor=editor.user, owner=editor.user)


def test_every_change_lands_in_the_history(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin)
    before = campaign.events.count()

    services.change_status(campaign=campaign, status=CampaignStatus.LIVE,
                           actor=admin)
    services.update_campaign(campaign=campaign, actor=admin,
                             budget=Decimal("5000"))
    services.assign(campaign=campaign, actor=admin, owner=admin)

    assert campaign.events.count() == before + 3


def test_an_owner_and_several_people_can_work_on_it(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin)
    one = make_staff_member("one@heliograph.agency").user
    two = make_staff_member("two@heliograph.agency").user

    services.assign(campaign=campaign, actor=admin, owner=one,
                    assignees=[one, two])

    campaign.refresh_from_db()
    assert campaign.owner == one
    assert set(campaign.assignees.all()) == {one, two}


# ---------------------------------------------------------------------------
# Overdue
# ---------------------------------------------------------------------------


def test_a_campaign_past_its_end_date_is_flagged(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin,
                             ends_on=timezone.localdate() - timedelta(days=1))

    assert campaign.is_overdue
    assert campaign in list(selectors.overdue(admin))


def test_a_finished_campaign_is_not_overdue(admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin, status=CampaignStatus.LIVE,
                             ends_on=timezone.localdate() - timedelta(days=1))
    services.change_status(campaign=campaign, status=CampaignStatus.DONE,
                           actor=admin)

    campaign.refresh_from_db()
    assert not campaign.is_overdue


# ---------------------------------------------------------------------------
# Through the staff pages
# ---------------------------------------------------------------------------


def test_staff_can_create_a_campaign_from_the_client_page(client, admin, tenant):
    org, _user = tenant
    sign_in(client, admin)

    response = client.post(
        reverse("staff:campaign_create", args=[org.slug]),
        {"name": "Spring push", "service_type": "paid_ads", "currency": "USD"},
    )

    assert response.status_code == 302
    campaign = Campaign.objects.get(organization=org, name="Spring push")
    assert campaign.status == CampaignStatus.PLANNED


# ---------------------------------------------------------------------------
# A service area's own fields — the generic detail-edit slot
# ---------------------------------------------------------------------------


def test_staff_can_set_the_platform_and_objective_of_a_paid_campaign(client, admin, tenant):
    from apps.paid_ads.models import PaidAdsCampaignDetail

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    sign_in(client, admin)

    response = client.post(
        reverse("staff:campaign_detail_update", args=[campaign.pk]),
        {"platform": "meta", "objective": "awareness"},
    )

    assert response.status_code == 302
    detail = PaidAdsCampaignDetail.objects.get(campaign=campaign)
    assert detail.platform == "meta"
    assert detail.objective == "awareness"


def test_the_detail_form_can_correct_an_existing_platform(client, admin, tenant):
    from apps.paid_ads.models import CampaignObjective, PaidAdsCampaignDetail

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    PaidAdsCampaignDetail.objects.create(
        campaign=campaign, platform="google", objective=CampaignObjective.TRAFFIC)
    sign_in(client, admin)

    client.post(
        reverse("staff:campaign_detail_update", args=[campaign.pk]),
        {"platform": "meta", "objective": "sales"},
    )

    detail = PaidAdsCampaignDetail.objects.get(campaign=campaign)
    assert detail.platform == "meta"
    assert detail.objective == "sales"
    assert PaidAdsCampaignDetail.objects.filter(campaign=campaign).count() == 1


def test_a_service_area_with_no_detail_form_registered_is_a_404(client, admin, tenant):
    """SEO has a detail model but, today, no edit form for it — the
    endpoint must refuse rather than silently doing nothing."""
    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="seo")
    sign_in(client, admin)

    response = client.post(
        reverse("staff:campaign_detail_update", args=[campaign.pk]),
        {"platform": "meta"},
    )

    assert response.status_code == 404


def test_staff_assigned_elsewhere_cannot_set_another_clients_campaign_detail(client, admin, tenant):
    from apps.staff.tests.factories import assign_client, make_role, make_staff_member

    org_a, _user_a = tenant
    org_b = make_org("Northwind Supply")
    campaign_b = make_campaign(org_b, actor=admin, service_type="paid_ads")
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "campaigns_edit",
                                       "organizations_view"])],
    )
    assign_client(staff, org_a)
    sign_in(client, staff.user)

    response = client.post(
        reverse("staff:campaign_detail_update", args=[campaign_b.pk]),
        {"platform": "meta", "objective": "awareness"},
    )

    assert response.status_code == 404


def test_the_campaign_page_renders_an_editable_form_for_a_paid_campaign(client, admin, tenant):
    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    sign_in(client, admin)

    body = client.get(reverse("staff:campaign_detail", args=[campaign.pk])).content

    assert b'name="platform"' in body
    assert b'name="objective"' in body


# ---------------------------------------------------------------------------
# Mapping a campaign to its real external counterpart
# ---------------------------------------------------------------------------


def test_staff_can_map_a_campaign_to_an_external_campaign_id(client, admin, tenant):
    from apps.integrations.models import ExternalCampaignReference
    from apps.integrations.tests.factories import make_connection

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    connection = make_connection(provider="meta_ads", organization=org, actor=admin)
    sign_in(client, admin)

    response = client.post(
        reverse("staff:campaign_map_external", args=[campaign.pk]),
        {"connection": connection.pk, "external_campaign_id": "act_123:camp_456"},
    )

    assert response.status_code == 302
    mapping = ExternalCampaignReference.objects.get(campaign=campaign)
    assert mapping.connection_id == connection.pk
    assert mapping.external_campaign_id == "act_123:camp_456"


def test_a_campaign_cannot_be_mapped_to_another_clients_connection_from_this_page(client, admin,
                                                                                  tenant):
    from apps.integrations.models import ExternalCampaignReference
    from apps.integrations.tests.factories import make_connection

    org, _user = tenant
    other_org = make_org("Northwind Supply")
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    # The form only ever offers this client's own connections (plus any
    # agency-wide one), so the only way to reach this is a forged POST —
    # exactly what has to still be refused.
    theirs = make_connection(provider="meta_ads", organization=other_org, actor=admin)
    sign_in(client, admin)

    response = client.post(
        reverse("staff:campaign_map_external", args=[campaign.pk]),
        {"connection": theirs.pk, "external_campaign_id": "camp_1"},
    )

    assert not ExternalCampaignReference.objects.filter(campaign=campaign).exists()
    assert response.status_code == 302  # redirected back with an error message


def test_the_mapping_form_only_offers_this_clients_own_connections(client, admin, tenant):
    from apps.integrations.tests.factories import make_connection

    org, _user = tenant
    other_org = make_org("Northwind Supply")
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    make_connection(provider="meta_ads", organization=org, actor=admin,
                    display_name="Ours")
    make_connection(provider="meta_ads", organization=other_org, actor=admin,
                    display_name="Theirs")
    sign_in(client, admin)

    body = client.get(reverse("staff:campaign_detail", args=[campaign.pk])).content

    assert b"Ours" in body
    assert b"Theirs" not in body


def test_staff_assigned_elsewhere_cannot_map_another_clients_campaign(client, admin, tenant):
    from apps.integrations.models import ExternalCampaignReference
    from apps.integrations.tests.factories import make_connection
    from apps.staff.tests.factories import assign_client, make_role, make_staff_member

    org_a, _user_a = tenant
    org_b = make_org("Northwind Supply")
    campaign_b = make_campaign(org_b, actor=admin, service_type="paid_ads")
    connection_b = make_connection(provider="meta_ads", organization=org_b, actor=admin)
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Campaigns", ["campaigns_view", "campaigns_edit",
                                       "organizations_view"])],
    )
    assign_client(staff, org_a)
    sign_in(client, staff.user)

    response = client.post(
        reverse("staff:campaign_map_external", args=[campaign_b.pk]),
        {"connection": connection_b.pk, "external_campaign_id": "camp_1"},
    )

    assert response.status_code == 404
    assert not ExternalCampaignReference.objects.filter(campaign=campaign_b).exists()


def test_the_list_combines_every_service_area(client, admin, tenant):
    """What the supplied dashboard shows: one view, every service."""
    org, _user = tenant
    seo = make_campaign(org, actor=admin, name="Search work", service_type="seo")
    ads = make_campaign(org, actor=admin, name="Ad work", service_type="paid_ads")
    sign_in(client, admin)

    body = client.get(reverse("staff:module_campaigns")).content

    assert seo.name.encode() in body
    assert ads.name.encode() in body


def test_the_list_can_be_filtered_by_service_area(client, admin, tenant):
    org, _user = tenant
    seo = make_campaign(org, actor=admin, name="Search work", service_type="seo")
    ads = make_campaign(org, actor=admin, name="Ad work", service_type="paid_ads")
    sign_in(client, admin)

    body = client.get(reverse("staff:module_campaigns"), {"type": "seo"}).content

    assert seo.name.encode() in body
    assert ads.name.encode() not in body


def test_the_list_can_be_filtered_by_status(client, admin, tenant):
    org, _user = tenant
    planned = make_campaign(org, actor=admin, name="Planned work")
    live = make_campaign(org, actor=admin, name="Live work", service_type="seo",
                         status=CampaignStatus.LIVE)
    sign_in(client, admin)

    body = client.get(reverse("staff:module_campaigns"),
                      {"status": CampaignStatus.LIVE}).content

    assert live.name.encode() in body
    assert planned.name.encode() not in body


def test_the_list_can_be_searched(client, admin, tenant):
    org, _user = tenant
    wanted = make_campaign(org, actor=admin, name="Findable campaign")
    other = make_campaign(org, actor=admin, name="Something else",
                          service_type="seo")
    sign_in(client, admin)

    body = client.get(reverse("staff:module_campaigns"), {"q": "Findable"}).content

    assert wanted.name.encode() in body
    assert other.name.encode() not in body


def test_the_mine_filter_includes_campaigns_someone_is_working_on(admin, tenant):
    """Not only the ones they own — being on a campaign counts."""
    from apps.staff.tests.factories import assign_client

    org, _user = tenant
    worker = make_staff_member(
        "worker@heliograph.agency",
        roles=[make_role("Worker", ["campaigns_view"])],
    )
    # Assigned to the client as well as holding the permission. Without
    # the assignment they would see nothing at all, which is correct and
    # would make this test pass for the wrong reason.
    assign_client(worker, org)
    mine = make_campaign(org, actor=admin, name="Theirs")
    make_campaign(org, actor=admin, name="Not theirs", service_type="seo")
    services.assign(campaign=mine, actor=admin, assignees=[worker.user])

    found = selectors.visible_campaigns(admin, owner="me")

    assert mine.pk not in {c.pk for c in found}, "admin is not on it"

    found_for_worker = selectors.visible_campaigns(worker.user, owner="me")
    assert [c.pk for c in found_for_worker] == [mine.pk]


# ---------------------------------------------------------------------------
# What the client sees
# ---------------------------------------------------------------------------


def _with_active_service(org, admin, *, category="paid"):  # noqa: ANN001, ANN202
    from apps.subscriptions.models import SubscriptionStatus
    from apps.subscriptions.tests.factories import make_service, make_subscription

    modules = {"paid": "paid_ads", "search": "seo"}
    return make_subscription(
        org, actor=admin,
        service=make_service(f"{category} service", category_slug=category,
                             workspace_module=modules[category]),
        status=SubscriptionStatus.ACTIVE,
    )


def test_a_client_sees_their_campaigns_in_the_combined_area(client, admin, tenant):
    org, user = tenant
    _with_active_service(org, admin)
    campaign = make_campaign(org, actor=admin, name="Spring push",
                             status=CampaignStatus.LIVE)
    sign_in(client, user)

    body = client.get(
        reverse("organizations:portal_module", args=["campaigns"])).content

    assert campaign.name.encode() in body
    assert b"Running now" in body


def test_a_service_area_shows_only_its_own_campaigns(client, admin, tenant):
    """The same query, filtered — not a second code path."""
    org, user = tenant
    _with_active_service(org, admin, category="paid")
    ads = make_campaign(org, actor=admin, name="Ad work", service_type="paid_ads",
                        status=CampaignStatus.LIVE)
    make_campaign(org, actor=admin, name="Search work", service_type="seo",
                  status=CampaignStatus.LIVE)
    sign_in(client, user)

    body = client.get(
        reverse("organizations:portal_module", args=["paid_ads"])).content

    assert ads.name.encode() in body
    assert b"Search work" not in body


def test_a_client_sees_the_summary_written_for_them(client, admin, tenant):
    org, user = tenant
    campaign = make_campaign(org, actor=admin,
                             client_summary="We are testing three new audiences.")
    sign_in(client, user)

    body = client.get(
        reverse("organizations:campaign_detail", args=[campaign.pk])).content

    assert b"three new audiences" in body


def test_a_client_with_no_campaigns_is_told_so_not_shown_zeroes(client, admin, tenant):
    org, user = tenant
    _with_active_service(org, admin)
    sign_in(client, user)

    body = client.get(
        reverse("organizations:portal_module", args=["campaigns"])).content

    assert b"Nothing running here yet" in body


# ---------------------------------------------------------------------------
# A client's own campaign performance (sections 17-19 of the analytics brief)
# ---------------------------------------------------------------------------


def _paid_ads_campaign_with_metrics(org, admin):
    from apps.paid_ads import services as paid_ads_services
    from apps.paid_ads.models import CampaignObjective, PaidAdsCampaignDetail

    campaign = make_campaign(org, actor=admin, name="October new collection",
                             service_type="paid_ads", status=CampaignStatus.LIVE)
    PaidAdsCampaignDetail.objects.create(
        campaign=campaign, platform="meta", objective=CampaignObjective.AWARENESS,
    )
    paid_ads_services.record_metrics(
        organization=org, campaign=campaign, actor=admin, date=date(2026, 1, 15),
        platform="meta", source="test", spend=Decimal("150"), impressions=10000,
        clicks=200, leads=5, conversions=2, revenue=Decimal("0"), reach=6000,
    )
    return campaign


def test_a_client_sees_real_performance_numbers_on_their_own_campaign(client, admin, tenant):
    org, user = tenant
    _with_active_service(org, admin, category="paid")
    campaign = _paid_ads_campaign_with_metrics(org, admin)
    sign_in(client, user)

    response = client.get(
        reverse("organizations:campaign_detail", args=[campaign.pk]),
        {"range": "last_12_months"},
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert "USD 150.00" in body
    assert "6,000" in body  # reach, the awareness objective's own KPI
    assert "Meta" in body


def test_a_client_with_no_recorded_results_sees_an_honest_empty_state(client, admin, tenant):
    org, user = tenant
    _with_active_service(org, admin, category="paid")
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    sign_in(client, user)

    body = client.get(
        reverse("organizations:campaign_detail", args=[campaign.pk])).content

    assert b"No reporting data is available yet" in body
    assert b"USD" not in body


def test_a_non_paid_ads_campaign_shows_no_performance_section(client, admin, tenant):
    org, user = tenant
    _with_active_service(org, admin, category="search")
    campaign = make_campaign(org, actor=admin, service_type="seo")
    sign_in(client, user)

    body = client.get(
        reverse("organizations:campaign_detail", args=[campaign.pk])).content

    assert b"Performance" not in body


def test_another_clients_campaign_performance_never_leaks_through_this_page(client, admin,
                                                                            tenant):
    """Section 59/TEST 5: a guessed or remembered id must return the same
    404 a nonexistent campaign would, carrying none of the other
    client's real numbers."""
    org, user = tenant
    _with_active_service(org, admin, category="paid")
    other_org = make_org("Northwind Supply")
    other_campaign = _paid_ads_campaign_with_metrics(other_org, admin)
    sign_in(client, user)

    response = client.get(
        reverse("organizations:campaign_detail", args=[other_campaign.pk]))

    assert response.status_code == 404
    assert b"150.00" not in response.content
    assert b"6,000" not in response.content
