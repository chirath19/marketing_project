import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.email_marketing import services
from apps.email_marketing.models import METRICS, EmailMetric, EmailWorkItem

pytestmark = pytest.mark.django_db


def test_staff_pages_and_forms_render(client, workspace):
    w = workspace
    client.force_login(w["staff"])
    urls = [
        reverse("staff:module_email_marketing"),
        reverse("staff:email_marketing_workspace", args=[w["org"].slug]),
        reverse("staff:email_marketing_create", args=[w["org"].slug]),
    ]
    for name in ["detail", "edit", "status", "metrics", "deliverable_create"]:
        urls.append(reverse(f"staff:email_marketing_{name}", args=[w["org"].slug, w["work"].pk]))
    urls.append(
        reverse(
            "staff:email_marketing_deliverable_edit",
            args=[w["org"].slug, w["work"].pk, w["delivery"].pk],
        )
    )
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url


@pytest.mark.parametrize("kind", ["campaign", "newsletter", "automation"])
def test_staff_creates_each_work_type_through_form(client, workspace, kind):
    w = workspace
    client.force_login(w["staff"])
    response = client.post(
        reverse("staff:email_marketing_create", args=[w["org"].slug]),
        {
            "campaign": w["campaign"].pk,
            "name": "Fresh work",
            "kind": kind,
            "client_visible": "on",
            "audience_size": 123,
            "trigger_description": "Signup → welcome",
        },
    )
    assert response.status_code == 302
    detail = client.get(response.url)
    assert detail.status_code == 200
    assert detail.context["work"].kind == kind
    assert detail.context["work"].audience_size == 123


def test_full_deliverable_review_and_execution_http_workflow(client, workspace, mailoutbox):
    w = workspace
    client.force_login(w["staff"])
    url = reverse(
        "staff:email_marketing_request_review", args=[w["org"].slug, w["work"].pk, w["delivery"].pk]
    )
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 302
    approval = w["delivery"].approvals.get()
    client.force_login(w["user"])
    assert (
        client.get(reverse("organizations:email_marketing_review", args=[approval.pk])).status_code
        == 200
    )
    assert (
        client.post(
            reverse("organizations:email_marketing_review", args=[approval.pk]),
            {"decision": "approved", "feedback": "Ready"},
        ).status_code
        == 302
    )
    client.force_login(w["staff"])
    response = client.post(
        reverse("staff:email_marketing_status", args=[w["org"].slug, w["work"].pk]),
        {
            "status": "completed",
            "executed_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "execution_note": "Sent externally: report 456",
        },
    )
    assert response.status_code == 302
    w["work"].refresh_from_db()
    assert w["work"].status == "completed"
    assert mailoutbox == []


def test_create_deliverable_and_stale_edit_through_forms(client, workspace, review):
    w = workspace
    client.force_login(w["staff"])
    response = client.post(
        reverse("staff:email_marketing_deliverable_create", args=[w["org"].slug, w["work"].pk]),
        {
            "name": "Subject variants",
            "description": "Two options",
            "client_visible": "on",
            "approval_required": "on",
        },
    )
    assert response.status_code == 302
    assert b"Subject variants" in client.get(response.url).content
    url = reverse("staff:email_marketing_edit", args=[w["org"].slug, w["work"].pk])
    data = {
        "name": "New issue name",
        "kind": "newsletter",
        "subject": "New subject",
        "client_visible": "on",
        "expected_revision": 1,
    }
    assert client.post(url, data).status_code == 302
    review.refresh_from_db()
    assert review.status == "cancelled"
    assert client.post(url, data).status_code == 400


def test_client_reports_exclude_internal_notes_and_escape_copy(client, workspace, executed):
    w = workspace
    services.save_work(
        actor=w["staff"],
        organization=w["org"],
        work=executed,
        expected_revision=1,
        internal_notes="INTERNAL SECRET",
        result_summary="Client report <script>alert(1)</script>",
    )
    services.record_metrics(
        actor=w["staff"],
        organization=w["org"],
        work=executed,
        date=timezone.localdate(),
        source="External report",
        **dict.fromkeys(METRICS, 7),
    )
    client.force_login(w["user"])
    report = client.get(reverse("organizations:portal_module", args=["email_marketing"]))
    assert report.status_code == 200
    assert report.context["totals"]["opens"] == 7
    detail = client.get(reverse("organizations:email_marketing_detail", args=[executed.pk]))
    assert detail.status_code == 200
    assert b"INTERNAL SECRET" not in detail.content
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in detail.content


def test_metric_form_creates_corrects_and_rejects_unexecuted_work(client, workspace, executed):
    w = workspace
    client.force_login(w["staff"])
    url = reverse("staff:email_marketing_metrics", args=[w["org"].slug, executed.pk])
    data = {"date": timezone.localdate(), "source": "Report", **dict.fromkeys(METRICS, 0)}
    assert client.post(url, data).status_code == 302
    data["opens"] = 8
    assert client.post(url, data).status_code == 302
    assert EmailMetric.objects.get().opens == 8
    unexecuted = services.save_work(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        kind="campaign",
        name="Not yet executed",
    )
    assert (
        client.post(
            reverse("staff:email_marketing_metrics", args=[w["org"].slug, unexecuted.pk]), data
        ).status_code
        == 400
    )


def test_invalid_filter_reports_error_and_retains_input(client, workspace):
    w = workspace
    client.force_login(w["user"])
    response = client.get(
        reverse("organizations:portal_module", args=["email_marketing"]),
        {"start": "2026-06-30", "end": "2026-06-01"},
    )
    assert response.status_code == 400
    assert b"2026-06-30" in response.content


def test_results_summary_editable_after_execution_in_http_form(client, workspace, executed):
    w = workspace
    client.force_login(w["staff"])
    url = reverse("staff:email_marketing_edit", args=[w["org"].slug, executed.pk])
    assert (
        client.post(
            url,
            {
                "expected_revision": 1,
                "result_summary": "Strong results",
                "internal_notes": "Private note",
            },
        ).status_code
        == 302
    )
    executed.refresh_from_db()
    assert executed.result_summary == "Strong results"
    assert executed.subject == "October update"


def test_client_decision_needs_csrf(workspace, review):
    client = Client(enforce_csrf_checks=True)
    client.force_login(workspace["user"])
    response = client.post(
        reverse("organizations:email_marketing_review", args=[review.pk]), {"decision": "approved"}
    )
    assert response.status_code == 403


def test_no_work_seeded_into_empty_workspace(client, workspace):
    w = workspace
    services.save_work(
        actor=w["staff"],
        organization=w["org"],
        work=w["work"],
        expected_revision=1,
        client_visible=False,
    )
    client.force_login(w["user"])
    report = client.get(reverse("organizations:portal_module", args=["email_marketing"]))
    assert report.context["work_count"] == 0
    assert report.context["totals"]["opens"] is None
    assert EmailWorkItem.objects.count() == 1
