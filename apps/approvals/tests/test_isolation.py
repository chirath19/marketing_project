import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.approvals import policies, selectors, services
from apps.notifications.models import Notification
from apps.organizations.models import OrganizationMember
from apps.organizations.tests.factories import make_member, make_tenant
from apps.staff.tests.factories import assign_client, make_role, make_staff_member
from apps.subscriptions.tests.factories import make_service, make_subscription

pytestmark = pytest.mark.django_db


def test_other_tenant_cannot_read_comment_or_decide(client, workspace, approval):
    w = workspace
    other, outsider = make_tenant("Other approval client")
    make_subscription(
        other,
        actor=w["admin"],
        service=make_service(
            "Other social", category_slug="other-approval", workspace_module="social"
        ),
    )
    assert not selectors.requests_for(outsider, other).exists()
    client.force_login(outsider)
    for action, data in [
        ("detail", None),
        ("comment", {"body": "Intrusion"}),
        ("decide", {"decision": "approved"}),
    ]:
        url = reverse(f"organizations:approval_{action}", args=[approval.pk])
        response = client.get(url) if data is None else client.post(url, data)
        assert response.status_code == 404
    assert not approval.comments.exists()
    assert approval.history.count() == 1


def test_staff_assignment_applies_to_inbox_detail_writes_and_notifications(
    client, workspace, approval
):
    w = workspace
    unassigned = make_staff_member(
        email="unassigned-approval@example.com",
        roles=[
            make_role(
                "Unassigned approvals", ["approvals_view", "approvals_create", "approvals_approve"]
            )
        ],
    )
    assert not selectors.requests_for(unassigned.user).exists()
    client.force_login(unassigned.user)
    assert client.get(reverse("staff:approval_detail", args=[approval.pk])).status_code == 404
    assert (
        client.post(
            reverse("staff:approval_comment", args=[approval.pk]), {"body": "No access"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("staff:approval_cancel", args=[approval.pk]), {"reason": "No access"}
        ).status_code
        == 404
    )
    with pytest.raises(PermissionDenied):
        services.create_request(
            actor=unassigned.user, organization=w["org"], campaign=w["campaign"], title="No access"
        )
    services.add_comment(
        actor=w["user"], organization=w["org"], request=approval, body="A real comment"
    )
    assert not Notification.objects.filter(recipient=unassigned.user, category="approval").exists()


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_reviewing_roles_can_comment_and_decide(workspace, approval, role):
    w = workspace
    OrganizationMember.objects.filter(user=w["user"]).update(role=role)
    services.add_comment(actor=w["user"], organization=w["org"], request=approval, body="Question")
    result = services.decide(
        actor=w["user"], organization=w["org"], request=approval, decision="approved"
    )
    assert result.status == "approved"


def test_viewers_can_only_read(client, workspace, approval):
    w = workspace
    OrganizationMember.objects.filter(user=w["user"]).update(role="viewer")
    client.force_login(w["user"])
    assert (
        client.get(reverse("organizations:approval_detail", args=[approval.pk])).status_code == 200
    )
    assert (
        client.post(
            reverse("organizations:approval_comment", args=[approval.pk]), {"body": "Not allowed"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            reverse("organizations:approval_decide", args=[approval.pk]), {"decision": "approved"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("revoke", ["membership", "organization", "subscription"])
def test_revocation_closes_access_and_stops_notifications(client, workspace, approval, revoke):
    w = workspace
    if revoke == "membership":
        OrganizationMember.objects.filter(user=w["user"]).update(status="removed")
    elif revoke == "organization":
        w["org"].status = "suspended"
        w["org"].save()
    else:
        w["subscription"].status = "paused"
        w["subscription"].save()
    Notification.objects.filter(category="approval").delete()
    client.force_login(w["user"])
    assert (
        client.get(reverse("organizations:approval_detail", args=[approval.pk])).status_code == 403
    )
    services.add_comment(
        actor=w["staff"], organization=w["org"], request=approval, body="Staff record"
    )
    assert not Notification.objects.filter(recipient=w["user"], category="approval").exists()


def test_selected_organization_is_enforced(client, workspace, approval):
    w = workspace
    other, _ = make_tenant("Other membership")
    make_member(other, w["user"])
    client.force_login(w["user"])
    session = client.session
    session["active_organization_id"] = other.pk
    session.save()
    assert (
        client.get(reverse("organizations:approval_detail", args=[approval.pk])).status_code == 403
    )
    assert not selectors.pending_for(w["user"], other).exists()


def test_read_only_staff_cannot_comment_or_cancel(workspace, approval):
    w = workspace
    profile = make_staff_member(
        email="approval-reader@example.com",
        roles=[make_role("Approval reader", ["approvals_view"])],
    )
    assign_client(profile, w["org"])
    assert policies.can_read(profile.user, approval)
    with pytest.raises(PermissionDenied):
        services.add_comment(
            actor=profile.user, organization=w["org"], request=approval, body="No write permission"
        )
    with pytest.raises(PermissionDenied):
        services.cancel(
            actor=profile.user,
            organization=w["org"],
            request=approval,
            reason="No write permission",
        )


def test_source_visibility_and_entitlement_are_not_bypassed(
    client, workspace, social_work, email_work
):
    from apps.social import services as social

    w = workspace
    content, delivery = social_work
    review = social.request_review(actor=w["staff"], organization=w["org"], deliverable=delivery)
    request = review.approval_request
    client.force_login(w["user"])
    assert (
        client.get(reverse("organizations:approval_detail", args=[request.pk])).status_code == 200
    )
    # Email remains active, so the shared approval area is still open.
    w["subscription"].status = "paused"
    w["subscription"].save()
    assert (
        client.get(reverse("organizations:approval_detail", args=[request.pk])).status_code == 404
    )
    w["subscription"].status = "active"
    w["subscription"].save()
    social.save_deliverable(
        actor=w["staff"],
        organization=w["org"],
        content=content,
        deliverable=delivery,
        expected_revision=1,
        client_visible=False,
    )
    assert (
        client.get(reverse("organizations:approval_detail", args=[request.pk])).status_code == 404
    )


def test_in_app_notifications_are_pointers_not_copies(workspace, approval):
    assert Notification.objects.filter(category="approval").exists()
    for notification in Notification.objects.filter(category="approval"):
        assert approval.description not in notification.body
        assert approval.title not in notification.title
        assert str(approval.pk) in notification.url


def test_reclassifying_campaign_cannot_bypass_source_entitlement(
    workspace, social_work, email_work
):
    from apps.campaigns.models import Campaign
    from apps.social import services as social

    w = workspace
    _, delivery = social_work
    review = social.request_review(actor=w["staff"], organization=w["org"], deliverable=delivery)
    Campaign.objects.filter(pk=w["campaign"].pk).update(service_type="email_marketing")
    w["subscription"].status = "paused"
    w["subscription"].save()
    request = review.approval_request
    request.refresh_from_db()
    assert not policies.can_read(w["user"], request)
    assert not selectors.requests_for(w["user"], w["org"]).filter(pk=request.pk).exists()
