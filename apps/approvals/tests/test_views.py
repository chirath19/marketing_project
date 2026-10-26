import pytest
from django.test import Client
from django.urls import reverse

from apps.approvals import services
from apps.approvals.models import ApprovalRequest
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_staff_inbox_create_and_detail(client, workspace, approval):
    w = workspace
    client.force_login(w["staff"])
    assert client.get(reverse("staff:module_approvals")).status_code == 200
    assert client.get(reverse("staff:approval_detail", args=[approval.pk])).status_code == 200
    url = reverse("staff:approval_create", args=[w["org"].slug])
    assert client.get(url).status_code == 200
    response = client.post(
        url, {"campaign": w["campaign"].pk, "title": "Approve scope", "description": "Final scope"}
    )
    assert response.status_code == 302
    assert b"Final scope" in client.get(response.url).content
    assert ApprovalRequest.objects.count() == 2


@pytest.mark.parametrize("decision", ["approved", "changes_requested", "rejected"])
def test_client_decisions_and_comments_through_http(client, workspace, approval, decision):
    w = workspace
    client.force_login(w["user"])
    assert client.get(reverse("organizations:portal_module", args=["approvals"])).status_code == 200
    assert (
        client.get(reverse("organizations:approval_detail", args=[approval.pk])).status_code == 200
    )
    assert (
        client.post(
            reverse("organizations:approval_comment", args=[approval.pk]),
            {"body": "A client comment <script>alert(1)</script>"},
        ).status_code
        == 302
    )
    response = client.post(
        reverse("organizations:approval_decide", args=[approval.pk]),
        {"decision": decision, "response": "My response"},
    )
    assert response.status_code == 302
    detail = client.get(response.url)
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in detail.content
    approval.refresh_from_db()
    assert approval.status == decision
    assert approval.history.count() == 3
    assert (
        client.post(
            reverse("organizations:approval_decide", args=[approval.pk]), {"decision": "approved"}
        ).status_code
        == 400
    )


def test_staff_comment_and_cancel(client, workspace, approval):
    w = workspace
    client.force_login(w["staff"])
    assert (
        client.post(
            reverse("staff:approval_comment", args=[approval.pk]), {"body": "Staff response"}
        ).status_code
        == 302
    )
    assert (
        client.post(
            reverse("staff:approval_cancel", args=[approval.pk]), {"reason": "Revised scope"}
        ).status_code
        == 302
    )
    approval.refresh_from_db()
    assert approval.status == "cancelled"
    assert approval.history.count() == 3


def test_dashboard_indicators_follow_status(client, workspace, approval):
    w = workspace
    client.force_login(w["staff"])
    response = client.get(reverse("staff:dashboard"))
    assert response.status_code == 200
    stat = next(
        item for item in response.context["stats"] if item["label"] == "Pending client approvals"
    )
    assert stat["value"] == 1
    assert approval.title.encode() in response.content
    client.force_login(w["user"])
    overview = client.get(reverse("organizations:overview"))
    assert overview.context["pending_approval_count"] == 1
    assert b"You are all caught up" not in overview.content
    services.decide(actor=w["user"], organization=w["org"], request=approval, decision="approved")
    assert client.get(reverse("organizations:overview")).context["pending_approval_count"] == 0
    client.force_login(w["staff"])
    response = client.get(reverse("staff:dashboard"))
    stat = next(
        item for item in response.context["stats"] if item["label"] == "Pending client approvals"
    )
    assert stat["value"] == 0
    assert Notification.objects.filter(
        recipient=w["staff"], category="approval", read_at__isnull=True
    ).exists()


def test_inbox_filters_history_and_invalid_values(client, workspace, approval):
    w = workspace
    services.decide(actor=w["user"], organization=w["org"], request=approval, decision="approved")
    client.force_login(w["user"])
    url = reverse("organizations:portal_module", args=["approvals"])
    assert client.get(url).context["page_obj"].paginator.count == 0
    assert client.get(url, {"page": 2}).context["page_obj"].paginator.count == 0
    assert client.get(url, {"status": "approved"}).context["page_obj"].paginator.count == 1
    assert client.get(url, {"status": ""}).context["page_obj"].paginator.count == 1
    assert client.get(url, {"status": "invalid"}).status_code == 400


def test_mutations_require_post_and_csrf(workspace, approval):
    w = workspace
    client = Client(enforce_csrf_checks=True)
    client.force_login(w["user"])
    for action, data in [("comment", {"body": "Comment"}), ("decide", {"decision": "approved"})]:
        url = reverse(f"organizations:approval_{action}", args=[approval.pk])
        assert client.get(url).status_code == 405
        assert client.post(url, data).status_code == 403
    client.force_login(w["staff"])
    url = reverse("staff:approval_cancel", args=[approval.pk])
    assert client.get(url).status_code == 405
    assert client.post(url, {"reason": "Cancel"}).status_code == 403
