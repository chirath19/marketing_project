from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.social import selectors, services
from apps.social.models import METRICS, SocialApproval, SocialMetric
from apps.staff.tests.factories import assign_client, make_role, make_staff_member

pytestmark = pytest.mark.django_db


def test_review_snapshot_and_final_decision(workspace, review):
    w = workspace
    assert review.snapshot["caption"] == w["content"].caption
    decision = services.decide_review(
        actor=w["user"],
        organization=w["org"],
        approval=review,
        decision="approved",
        feedback="Looks good",
    )
    assert decision.decided_by == w["user"]
    assert decision.decided_at
    assert decision.feedback == "Looks good"
    with pytest.raises(ValidationError):
        services.decide_review(
            actor=w["user"],
            organization=w["org"],
            approval=review,
            decision="changes_requested",
            feedback="Too late",
        )


def test_changes_require_feedback_and_allow_a_new_round(workspace, review):
    w = workspace
    with pytest.raises(ValidationError):
        services.decide_review(
            actor=w["user"], organization=w["org"], approval=review, decision="changes_requested"
        )
    services.decide_review(
        actor=w["user"],
        organization=w["org"],
        approval=review,
        decision="changes_requested",
        feedback="Shorten the intro",
    )
    second = services.request_review(
        actor=w["staff"], organization=w["org"], deliverable=w["delivery"]
    )
    assert second.pk != review.pk
    assert SocialApproval.objects.count() == 2


def test_duplicate_pending_review_is_rejected(workspace, review):
    w = workspace
    with pytest.raises(ValidationError):
        services.request_review(actor=w["staff"], organization=w["org"], deliverable=w["delivery"])


@pytest.mark.parametrize("target", ["content", "delivery"])
def test_edits_cancel_pending_review_and_keep_submitted_snapshot(workspace, review, target):
    w = workspace
    if target == "content":
        services.save_content(
            actor=w["staff"],
            organization=w["org"],
            content=w["content"],
            expected_revision=1,
            caption="Updated copy",
        )
    else:
        services.save_deliverable(
            actor=w["staff"],
            organization=w["org"],
            content=w["content"],
            deliverable=w["delivery"],
            expected_revision=1,
            description="New cut",
        )
    review.refresh_from_db()
    assert review.status == "cancelled"
    assert review.snapshot["caption"] == "Our new collection"
    assert review.snapshot["description"] == "Thirty second launch video"
    with pytest.raises(ValidationError):
        services.decide_review(
            actor=w["user"], organization=w["org"], approval=review, decision="approved"
        )


@pytest.mark.parametrize("target", ["content", "delivery"])
def test_approved_revision_cannot_authorize_changed_work(workspace, review, target):
    w = workspace
    services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    services.change_status(
        actor=w["staff"], organization=w["org"], content=w["content"], status="scheduled"
    )
    if target == "content":
        services.save_content(
            actor=w["staff"],
            organization=w["org"],
            content=w["content"],
            expected_revision=1,
            caption="Changed",
        )
    else:
        services.save_deliverable(
            actor=w["staff"],
            organization=w["org"],
            content=w["content"],
            deliverable=w["delivery"],
            expected_revision=1,
            description="Changed",
        )
    w["content"].refresh_from_db()
    assert w["content"].status == "draft"
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"], organization=w["org"], content=w["content"], status="scheduled"
        )
    review.refresh_from_db()
    assert review.status == "approved"


def test_stale_edit_is_rejected(workspace):
    w = workspace
    with pytest.raises(ValidationError):
        services.save_content(
            actor=w["staff"],
            organization=w["org"],
            content=w["content"],
            expected_revision=0,
            caption="stale",
        )


def test_required_approvals_and_publication_evidence(workspace, review):
    w = workspace
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"], organization=w["org"], content=w["content"], status="published"
        )
    services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"], organization=w["org"], content=w["content"], status="published"
        )
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"],
            organization=w["org"],
            content=w["content"],
            status="published",
            published_at=timezone.now() + timedelta(days=1),
            published_url="https://example.com/post",
        )


def test_publishing_needs_publish_permission(workspace, review):
    w = workspace
    services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    profile = make_staff_member(
        email="editor@example.com",
        roles=[make_role("Social editor", ["social_view", "social_edit"])],
    )
    assign_client(profile, w["org"])
    with pytest.raises(PermissionDenied):
        services.change_status(
            actor=profile.user,
            organization=w["org"],
            content=w["content"],
            status="published",
            published_at=timezone.now(),
            published_url="https://example.com/post",
        )


def test_published_work_is_preserved(workspace, published):
    w = workspace
    with pytest.raises(ValidationError):
        services.save_content(
            actor=w["staff"],
            organization=w["org"],
            content=published,
            expected_revision=1,
            caption="rewrite",
        )
    with pytest.raises(ValidationError):
        services.save_deliverable(
            actor=w["staff"], organization=w["org"], content=published, title="New asset"
        )


def test_results_are_daily_correctable_and_filterable(workspace, published):
    w = workspace
    today = timezone.localdate()
    args = {
        "actor": w["staff"],
        "organization": w["org"],
        "content": published,
        "source": "Platform daily export",
    }
    services.record_metrics(**args, date=today, **dict.fromkeys(METRICS, 4))
    services.record_metrics(**args, date=today - timedelta(days=1), **dict.fromkeys(METRICS, 3))
    services.record_metrics(**args, date=today, **dict.fromkeys(METRICS, 5))
    assert SocialMetric.objects.count() == 2
    report = selectors.workspace(w["user"], w["org"], {"start": today, "end": today})
    assert report["totals"]["impressions"] == 5
    assert report["results"].count() == 1
    assert selectors.workspace(w["user"], w["org"], {})["totals"]["impressions"] == 8


@pytest.mark.parametrize("bad", [-1, 1.5, Decimal("NaN"), "Infinity"])
def test_invalid_measures_rejected(workspace, published, bad):
    w = workspace
    values = dict.fromkeys(METRICS, 0)
    values["likes"] = bad
    with pytest.raises(ValidationError):
        services.record_metrics(
            actor=w["staff"],
            organization=w["org"],
            content=published,
            date=timezone.localdate(),
            source="Export",
            **values,
        )
    assert not SocialMetric.objects.exists()


def test_metrics_require_published_content_and_observation_date(workspace):
    w = workspace
    with pytest.raises(ValidationError):
        services.record_metrics(
            actor=w["staff"],
            organization=w["org"],
            content=w["content"],
            date=timezone.localdate(),
            source="Export",
            **dict.fromkeys(METRICS, 0),
        )


def test_channel_identity_is_stable_once_used(workspace):
    w = workspace
    with pytest.raises(ValidationError):
        services.save_channel(
            actor=w["staff"], organization=w["org"], channel=w["channel"], platform="linkedin"
        )
    services.save_channel(
        actor=w["staff"], organization=w["org"], channel=w["channel"], is_active=False
    )


def test_no_data_is_not_zero(workspace):
    w = workspace
    assert selectors.workspace(w["user"], w["org"], {})["totals"]["impressions"] is None


@pytest.mark.parametrize("days", [-10, 1])
def test_results_cannot_precede_publication_or_be_future(workspace, published, days):
    w = workspace
    with pytest.raises(ValidationError):
        services.record_metrics(
            actor=w["staff"],
            organization=w["org"],
            content=published,
            date=timezone.localdate() + timedelta(days=days),
            source="Daily report",
            **dict.fromkeys(METRICS, 0),
        )


def test_correction_requires_edit_permission(workspace, published):
    w = workspace
    profile = make_staff_member(
        email="recorder@example.com", roles=[make_role("Social recorder", ["social_create"])]
    )
    assign_client(profile, w["org"])
    values = {
        "actor": profile.user,
        "organization": w["org"],
        "content": published,
        "date": timezone.localdate(),
        "source": "Daily report",
        **dict.fromkeys(METRICS, 0),
    }
    services.record_metrics(**values)
    with pytest.raises(PermissionDenied):
        services.record_metrics(**values)
    assert SocialMetric.objects.count() == 1


def test_schedule_does_not_record_publication(workspace, review):
    w = workspace
    services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    content = services.change_status(
        actor=w["staff"], organization=w["org"], content=w["content"], status="scheduled"
    )
    assert content.published_at is None
    assert content.published_url == ""
    assert content.external_id == ""


def test_filters_and_unscheduled_work(workspace):
    w = workspace
    unscheduled = services.save_content(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        channel=w["channel"],
        title="Unscheduled",
        client_visible=True,
    )
    assert selectors.workspace(w["user"], w["org"], {})["content_count"] == 2
    assert (
        selectors.workspace(w["user"], w["org"], {"start": timezone.localdate()})["content_count"]
        == 1
    )
    assert (
        selectors.workspace(w["user"], w["org"], {"kind": "post"})["content_items"].get()
        == unscheduled
    )
    assert selectors.workspace(w["user"], w["org"], {"status": "published"})["content_count"] == 0
    assert (
        selectors.workspace(
            w["user"], w["org"], {"channel": w["channel"], "campaign": w["campaign"]}
        )["content_count"]
        == 2
    )


def test_delivery_requires_shared_parent_and_reviewable_content(workspace):
    w = workspace
    delivery = services.save_deliverable(
        actor=w["staff"],
        organization=w["org"],
        content=w["content"],
        title="Empty review",
        client_visible=True,
    )
    with pytest.raises(ValidationError):
        services.request_review(actor=w["staff"], organization=w["org"], deliverable=delivery)
    services.save_content(
        actor=w["staff"],
        organization=w["org"],
        content=w["content"],
        expected_revision=1,
        client_visible=False,
    )
    with pytest.raises(ValidationError):
        services.request_review(actor=w["staff"], organization=w["org"], deliverable=w["delivery"])
