import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.campaigns.tests.factories import make_campaign
from apps.organizations.models import OrganizationMember
from apps.organizations.tests.factories import make_member, make_tenant
from apps.social import selectors, services
from apps.social.models import METRICS
from apps.staff.tests.factories import make_role, make_staff_member

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "selector",
    [
        "campaigns_for",
        "channels_for",
        "partnerships_for",
        "content_for",
        "deliverables_for",
        "reviews_for",
        "metrics_for",
    ],
)
def test_every_selector_enforces_assignment_and_client_membership(workspace, published, selector):
    w = workspace
    services.save_partnership(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        creator_name="Creator",
        platform="instagram",
        client_visible=True,
    )
    from django.utils import timezone

    services.record_metrics(
        actor=w["staff"],
        organization=w["org"],
        content=published,
        date=timezone.localdate(),
        source="Export",
        **dict.fromkeys(METRICS, 1),
    )
    select = getattr(selectors, selector)
    assert select(w["staff"], w["org"]).exists()
    assert select(w["user"], w["org"]).exists()
    other_org, other_user = make_tenant("Other social client")
    assert not select(other_user, w["org"]).exists()
    assert not select(w["user"], other_org).exists()
    unassigned = make_staff_member(
        email="unassigned@example.com",
        roles=[make_role("Unassigned social", ["social_view", "social_edit"])],
    )
    assert not select(unassigned.user, w["org"]).exists()


def test_staff_cannot_decide_for_client(workspace, review):
    w = workspace
    with pytest.raises(PermissionDenied):
        services.decide_review(
            actor=w["admin"], organization=w["org"], approval=review, decision="approved"
        )


def test_viewer_can_read_but_not_review(client, workspace, review):
    w = workspace
    OrganizationMember.objects.filter(user=w["user"]).update(role="viewer")
    client.force_login(w["user"])
    url = reverse("organizations:social_review", args=[review.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {"decision": "approved"}).status_code == 403


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_active_reviewing_roles_can_approve(workspace, review, role):
    w = workspace
    OrganizationMember.objects.filter(user=w["user"]).update(role=role)
    result = services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    assert result.status == "approved"


@pytest.mark.parametrize("revoke", ["membership", "subscription", "organization"])
def test_revocation_blocks_pending_review(client, workspace, review, revoke):
    w = workspace
    if revoke == "membership":
        OrganizationMember.objects.filter(user=w["user"]).update(status="suspended")
    elif revoke == "subscription":
        w["subscription"].status = "paused"
        w["subscription"].save()
    else:
        w["org"].status = "suspended"
        w["org"].save()
    client.force_login(w["user"])
    assert (
        client.post(
            reverse("organizations:social_review", args=[review.pk]), {"decision": "approved"}
        ).status_code
        == 403
    )
    review.refresh_from_db()
    assert review.status == "pending"


def test_selected_organization_needs_its_own_entitlement(client, workspace):
    w = workspace
    other, _ = make_tenant("Other membership")
    make_member(other, w["user"])
    client.force_login(w["user"])
    session = client.session
    session["active_organization_id"] = other.pk
    session.save()
    assert client.get(reverse("organizations:portal_module", args=["social"])).status_code == 403


def test_clients_cannot_guess_internal_content_or_deliverables(client, workspace, review):
    w = workspace
    client.force_login(w["user"])
    services.save_deliverable(
        actor=w["staff"],
        organization=w["org"],
        content=w["content"],
        deliverable=w["delivery"],
        expected_revision=1,
        client_visible=False,
    )
    assert client.get(reverse("organizations:social_review", args=[review.pk])).status_code == 404
    assert (
        b"Final edit"
        not in client.get(reverse("organizations:social_detail", args=[w["content"].pk])).content
    )
    services.save_content(
        actor=w["staff"],
        organization=w["org"],
        content=w["content"],
        expected_revision=1,
        client_visible=False,
    )
    assert (
        client.get(reverse("organizations:social_detail", args=[w["content"].pk])).status_code
        == 404
    )


def test_cross_tenant_relationships_rejected(workspace):
    w = workspace
    other, _ = make_tenant("Other tenant")
    campaign = make_campaign(other, actor=w["admin"], service_type="social")
    with pytest.raises(ValidationError):
        services.save_content(
            actor=w["admin"],
            organization=w["org"],
            campaign=campaign,
            channel=w["channel"],
            title="Bad reference",
        )
    with pytest.raises(ValidationError):
        services.save_partnership(
            actor=w["admin"],
            organization=w["org"],
            campaign=campaign,
            creator_name="Wrong tenant",
            platform="instagram",
        )
    other_channel = services.save_channel(
        actor=w["admin"], organization=other, name="Other channel", platform="facebook"
    )
    with pytest.raises(ValidationError):
        services.save_content(
            actor=w["admin"],
            organization=w["org"],
            campaign=w["campaign"],
            channel=other_channel,
            title="Bad channel",
        )


def test_unassigned_staff_cannot_open_or_mutate_other_workspace(client, workspace):
    w = workspace
    other, _ = make_tenant("Unassigned organization")
    client.force_login(w["staff"])
    assert client.get(reverse("staff:social_workspace", args=[other.slug])).status_code == 404
    with pytest.raises(PermissionDenied):
        services.save_channel(
            actor=w["staff"], organization=other, name="Forbidden", platform="other"
        )


def test_private_partnership_and_notes_are_not_rendered(client, workspace):
    w = workspace
    partnership = services.save_partnership(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        creator_name="Private Creator",
        platform="instagram",
        internal_notes="Confidential terms",
    )
    content = services.save_content(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        channel=w["channel"],
        partnership=partnership,
        title="Shared creator reel",
        client_visible=True,
    )
    client.force_login(w["user"])
    body = client.get(reverse("organizations:social_detail", args=[content.pk])).content
    assert b"Private Creator" not in body
    assert b"Confidential terms" not in body
    assert not selectors.partnerships_for(w["user"], w["org"]).exists()


def test_other_tenant_review_url_and_post_are_hidden(client, workspace, review):
    other_org, outsider = make_tenant("Other reviewer")
    from apps.subscriptions.tests.factories import make_service, make_subscription

    make_subscription(
        other_org,
        actor=workspace["admin"],
        service=make_service(
            "Other social", category_slug="other-social", workspace_module="social"
        ),
    )
    client.force_login(outsider)
    url = reverse("organizations:social_review", args=[review.pk])
    assert client.get(url).status_code == 404
    assert client.post(url, {"decision": "approved"}).status_code == 404
