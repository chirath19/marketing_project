import pytest
from django.urls import reverse

from apps.social import services

pytestmark = pytest.mark.django_db


def test_staff_workspace_and_forms_render(client, workspace):
    w = workspace
    client.force_login(w["staff"])
    urls = [
        reverse("staff:module_social"),
        reverse("staff:social_workspace", args=[w["org"].slug]),
        reverse("staff:social_detail", args=[w["org"].slug, w["content"].pk]),
    ]
    for kind in ["channel", "partnership", "content"]:
        urls.append(reverse("staff:social_create", args=[w["org"].slug, kind]))
    for name in ["social_status", "social_deliverable_create"]:
        urls.append(reverse(f"staff:{name}", args=[w["org"].slug, w["content"].pk]))
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, (url, response.content[:400])


def test_staff_create_content_and_deliverable_through_forms(client, workspace):
    w = workspace
    client.force_login(w["staff"])
    response = client.post(
        reverse("staff:social_create", args=[w["org"].slug, "content"]),
        {
            "campaign": w["campaign"].pk,
            "channel": w["channel"].pk,
            "title": "New post",
            "kind": "post",
            "caption": "Copy",
            "client_visible": "on",
        },
    )
    assert response.status_code == 302
    detail = client.get(response.url)
    assert b"New post" in detail.content
    content = detail.context["content"]
    response = client.post(
        reverse("staff:social_deliverable_create", args=[w["org"].slug, content.pk]),
        {
            "title": "Artwork",
            "description": "Artwork brief",
            "client_visible": "on",
            "approval_required": "on",
        },
    )
    assert response.status_code == 302
    assert b"Artwork" in client.get(response.url).content


def test_client_sees_safe_work_and_can_review(client, workspace, review):
    w = workspace
    services.save_content(
        actor=w["staff"],
        organization=w["org"],
        content=w["content"],
        expected_revision=1,
        internal_notes="CONFIDENTIAL INTERNAL NOTE",
    )
    client.force_login(w["user"])
    workspace_response = client.get(reverse("organizations:portal_module", args=["social"]))
    assert workspace_response.status_code == 200
    assert b"Launch reel" in workspace_response.content
    detail = client.get(reverse("organizations:social_detail", args=[w["content"].pk]))
    assert detail.status_code == 200
    assert b"CONFIDENTIAL INTERNAL NOTE" not in detail.content
    url = reverse("organizations:social_review", args=[review.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {"decision": "approved"}).status_code == 302
    review.refresh_from_db()
    assert review.status == "approved"


def test_invalid_filters_preserve_errors(client, workspace):
    w = workspace
    client.force_login(w["staff"])
    assert (
        client.get(
            reverse("staff:social_workspace", args=[w["org"].slug]),
            {"start": "2026-02-10", "end": "2026-01-01"},
        ).status_code
        == 400
    )


def test_metrics_form_creates_and_corrects_daily_values(client, workspace, published):
    from django.utils import timezone

    from apps.social.models import METRICS, SocialMetric

    w = workspace
    client.force_login(w["staff"])
    url = reverse("staff:social_metrics", args=[w["org"].slug, published.pk])
    assert client.get(url).status_code == 200
    values = {"date": timezone.localdate(), "source": "Daily export", **dict.fromkeys(METRICS, 0)}
    assert client.post(url, values).status_code == 302
    values["likes"] = 3
    assert client.post(url, values).status_code == 302
    assert SocialMetric.objects.get().likes == 3


def test_review_request_is_post_only(client, workspace):
    w = workspace
    client.force_login(w["staff"])
    url = reverse(
        "staff:social_request_review", args=[w["org"].slug, w["content"].pk, w["delivery"].pk]
    )
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 302


def test_review_csrf_protected(workspace, review):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(workspace["user"])
    assert (
        client.post(
            reverse("organizations:social_review", args=[review.pk]), {"decision": "approved"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("kind", ["channel", "partnership", "content"])
def test_malformed_edit_identifier_is_not_a_server_error(client, workspace, kind):
    w = workspace
    client.force_login(w["staff"])
    assert (
        client.get(
            reverse("staff:social_edit", args=[w["org"].slug, kind, "not-an-id"])
        ).status_code
        == 404
    )


def test_existing_content_edit_form_preserves_version_check(client, workspace, review):
    w = workspace
    client.force_login(w["staff"])
    url = reverse("staff:social_edit", args=[w["org"].slug, "content", w["content"].pk])
    response = client.post(
        url,
        {
            "title": "New title",
            "kind": "reel",
            "caption": "New copy",
            "client_visible": "on",
            "expected_revision": 1,
        },
    )
    assert response.status_code == 302
    review.refresh_from_db()
    assert review.status == "cancelled"
    response = client.post(
        url,
        {"title": "Stale title", "kind": "reel", "client_visible": "on", "expected_revision": 1},
    )
    assert response.status_code == 400
    w["content"].refresh_from_db()
    assert w["content"].title == "New title"
