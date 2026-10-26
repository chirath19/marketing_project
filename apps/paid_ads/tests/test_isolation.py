from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.campaigns.tests.factories import make_campaign
from apps.organizations.middleware import SESSION_KEY
from apps.organizations.tests.factories import make_member, make_org, make_tenant
from apps.paid_ads import selectors, services
from apps.paid_ads.importers import import_metrics
from apps.paid_ads.models import DailyAdMetric, PaidAdsGoal
from apps.staff.tests.factories import assign_client, make_role, make_staff_member

pytestmark = pytest.mark.django_db


def test_querysets_and_selectors_isolate_both_models(workspace, record):
    metric = record()
    goal = services.save_goal(
        organization=workspace["org"],
        actor=workspace["staff"],
        title="Target",
        metric="leads",
        target=10,
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
        currency="USD",
    )
    other_org, outsider = make_tenant("Other client")
    for model, row in [(DailyAdMetric, metric), (PaidAdsGoal, goal)]:
        assert list(model.objects.visible_to(workspace["user"])) == [row]
        assert not model.objects.visible_to(outsider).exists()
        assert not model.objects.visible_to(AnonymousUser()).exists()
    assert not selectors.metrics_for(outsider, workspace["org"]).exists()
    assert not selectors.goals_for(outsider, workspace["org"]).exists()
    assert not selectors.metrics_for(workspace["staff"], other_org).exists()


def test_unassigned_staff_cannot_open_or_write_workspace(client, workspace, record):
    record()
    stranger = make_staff_member(
        "other@staff.example",
        roles=[
            make_role(
                "Other ads",
                [
                    "paid_ads_view",
                    "paid_ads_create",
                    "paid_ads_edit",
                ],
            )
        ],
    ).user
    client.force_login(stranger)
    for name in (
        "paid_ads_workspace",
        "paid_ads_record",
        "paid_ads_import",
        "paid_ads_goals",
        "paid_ads_goal_create",
    ):
        assert client.get(reverse("staff:" + name, args=[workspace["org"].slug])).status_code == 404
    with pytest.raises(PermissionDenied):
        record(actor=stranger)
    with pytest.raises(PermissionDenied):
        services.save_goal(organization=workspace["org"], actor=stranger, title="No")


def test_client_and_read_only_staff_cannot_write(client, workspace, record):
    viewer = make_staff_member(
        "viewer@staff.example",
        roles=[
            make_role(
                "Ads viewer",
                [
                    "paid_ads_view",
                ],
            )
        ],
    )
    assign_client(viewer, workspace["org"])
    for user in (workspace["user"], viewer.user):
        with pytest.raises(PermissionDenied):
            record(actor=user)
        client.force_login(user)
        assert (
            client.post(
                reverse("staff:paid_ads_record", args=[workspace["org"].slug]), {}
            ).status_code
            == 403
        )


def test_correction_requires_edit_and_import_rolls_back(workspace, record):
    from apps.paid_ads.tests.test_paid_ads import csv_file

    record()
    creator = make_staff_member(
        "creator@staff.example",
        roles=[
            make_role(
                "Ads creator",
                [
                    "paid_ads_view",
                    "paid_ads_create",
                ],
            )
        ],
    )
    assign_client(creator, workspace["org"])
    with pytest.raises(PermissionDenied):
        record(actor=creator.user)
    first = f"2026-01-02,{workspace['campaign'].pk},google,100,1000,100,10,5,400"
    existing = f"2026-01-01,{workspace['campaign'].pk},google,200,1000,100,10,5,400"
    with pytest.raises(PermissionDenied):
        import_metrics(
            actor=creator.user,
            organization=workspace["org"],
            source="Report",
            file_obj=csv_file(workspace, first, existing),
        )
    assert DailyAdMetric.objects.count() == 1
    assert DailyAdMetric.objects.get().spend == 100


def test_campaign_must_belong_to_same_client_and_paid_ads(workspace, record):
    other = make_campaign(make_org("Other"), actor=workspace["admin"])
    seo = make_campaign(workspace["org"], actor=workspace["admin"], service_type="seo")
    for campaign in (other, seo):
        with pytest.raises(ValidationError):
            record(campaign=campaign)
        with pytest.raises(ValidationError):
            services.save_goal(
                organization=workspace["org"],
                actor=workspace["staff"],
                title="Invalid",
                metric="leads",
                target=10,
                campaign=campaign,
                starts_on=date(2026, 1, 1),
                ends_on=date(2026, 1, 31),
                currency="USD",
            )


def test_removed_membership_and_paused_service_revoke_access(client, workspace, record):
    record()
    url = reverse("organizations:portal_module", args=["paid_ads"])
    client.force_login(workspace["user"])
    assert client.get(url).status_code == 200
    workspace["subscription"].status = "paused"
    workspace["subscription"].save(update_fields=["status"])
    assert client.get(url).status_code == 403
    workspace["subscription"].status = "active"
    workspace["subscription"].save(update_fields=["status"])
    workspace["org"].memberships.update(status="removed")
    assert client.get(url).status_code == 403


def test_suspended_organization_is_refused(client, workspace):
    workspace["org"].status = "suspended"
    workspace["org"].save(update_fields=["status"])
    client.force_login(workspace["user"])
    assert client.get(reverse("organizations:portal_module", args=["paid_ads"])).status_code == 403


def test_selected_organization_controls_entitlement_and_data(client, workspace, record):
    from apps.subscriptions.tests.factories import make_service, make_subscription

    record()
    other = make_org("Second client")
    make_member(other, workspace["user"])
    client.force_login(workspace["user"])
    session = client.session
    session[SESSION_KEY] = other.pk
    session.save()
    url = reverse("organizations:portal_module", args=["paid_ads"])
    assert client.get(url).status_code == 403
    make_subscription(
        other,
        actor=workspace["admin"],
        service=make_service(
            "Second Paid service", category_slug="second-paid", workspace_module="paid_ads"
        ),
    )
    response = client.get(url, {"start": "2026-01-01", "end": "2026-01-31"})
    assert response.status_code == 200
    assert not response.context["has_data"]
    assert b"Search acquisition" not in response.content
    response = client.get(url, {"campaign": workspace["campaign"].pk})
    assert response.status_code == 400


def test_filter_cannot_name_another_clients_campaign(client, workspace):
    campaign = make_campaign(make_org("Private"), actor=workspace["admin"], name="Secret campaign")
    client.force_login(workspace["staff"])
    response = client.get(
        reverse("staff:paid_ads_workspace", args=[workspace["org"].slug]), {"campaign": campaign.pk}
    )
    assert response.status_code == 400
    assert b"Secret campaign" not in response.content


def test_clients_never_see_internal_campaign_notes(client, workspace, record):
    workspace["campaign"].internal_notes = "CONFIDENTIAL AGENCY STRATEGY"
    workspace["campaign"].save(update_fields=["internal_notes"])
    record(source="INTERNAL REPORT FILE")
    client.force_login(workspace["user"])
    response = client.get(
        reverse("organizations:portal_module", args=["paid_ads"]),
        {"start": "2026-01-01", "end": "2026-01-31"},
    )
    assert b"CONFIDENTIAL" not in response.content
    assert b"INTERNAL REPORT FILE" not in response.content
    assert b"Manage campaign" not in response.content


def test_anonymous_and_staff_cannot_use_client_workspace(client, workspace):
    url = reverse("organizations:portal_module", args=["paid_ads"])
    assert client.get(url).status_code == 302
    client.force_login(workspace["staff"])
    assert client.get(url).status_code == 403
