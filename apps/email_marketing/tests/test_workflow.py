from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.email_marketing import selectors, services
from apps.email_marketing.models import METRICS, EmailApproval, EmailMetric, EmailWorkItem
from apps.staff.tests.factories import assign_client, make_role, make_staff_member

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind", ["campaign", "newsletter", "automation"])
def test_work_types_are_supported(workspace, kind):
    w = workspace
    work = services.save_work(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        name="New work",
        kind=kind,
        trigger_description="Signup → welcome → follow-up",
    )
    assert work.kind == kind
    assert work.status == "draft"
    assert work.audience_size is None
    assert work.client_visible is False


def test_review_preserves_snapshot_and_decision(workspace, review):
    w = workspace
    assert review.snapshot["subject"] == w["work"].subject
    assert review.snapshot["audience_size"] == 200
    approval = services.decide_review(
        actor=w["user"],
        organization=w["org"],
        approval=review,
        decision="approved",
        feedback="Ready",
    )
    assert approval.decided_by == w["user"]
    assert approval.decided_at is not None
    with pytest.raises(ValidationError):
        services.decide_review(
            actor=w["user"],
            organization=w["org"],
            approval=review,
            decision="changes_requested",
            feedback="Late",
        )


def test_changes_require_feedback_and_support_another_round(workspace, review):
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
        feedback="Change the heading",
    )
    second = services.request_review(
        actor=w["staff"], organization=w["org"], deliverable=w["delivery"]
    )
    assert second.pk != review.pk
    assert EmailApproval.objects.count() == 2


def test_duplicate_pending_review_rejected(workspace, review):
    w = workspace
    with pytest.raises(ValidationError):
        services.request_review(actor=w["staff"], organization=w["org"], deliverable=w["delivery"])


@pytest.mark.parametrize("target", ["work", "delivery"])
def test_pending_review_cancelled_by_edit(workspace, review, target):
    w = workspace
    if target == "work":
        services.save_work(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            expected_revision=1,
            subject="Changed subject",
        )
    else:
        services.save_deliverable(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            deliverable=w["delivery"],
            expected_revision=1,
            description="Updated layout",
        )
    review.refresh_from_db()
    assert review.status == "cancelled"
    assert review.snapshot["subject"] == "October update"
    with pytest.raises(ValidationError):
        services.decide_review(
            actor=w["user"], organization=w["org"], approval=review, decision="approved"
        )


@pytest.mark.parametrize("target", ["work", "delivery"])
def test_changed_revision_cannot_use_old_approval(workspace, review, target):
    w = workspace
    services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    services.change_status(
        actor=w["staff"], organization=w["org"], work=w["work"], status="scheduled"
    )
    if target == "work":
        services.save_work(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            expected_revision=1,
            brief="New copy",
        )
    else:
        services.save_deliverable(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            deliverable=w["delivery"],
            expected_revision=1,
            description="New design",
        )
    w["work"].refresh_from_db()
    assert w["work"].status == "draft"
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"], organization=w["org"], work=w["work"], status="scheduled"
        )
    review.refresh_from_db()
    assert review.status == "approved"


def test_stale_staff_edit_rejected(workspace):
    w = workspace
    with pytest.raises(ValidationError):
        services.save_work(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            expected_revision=0,
            subject="Stale",
        )
    with pytest.raises(ValidationError):
        services.save_deliverable(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            deliverable=w["delivery"],
            expected_revision=0,
            name="Stale",
        )


def test_required_approvals_gate_execution_and_scheduling(workspace):
    w = workspace
    for status in ["scheduled", "completed"]:
        with pytest.raises(ValidationError):
            services.change_status(
                actor=w["staff"], organization=w["org"], work=w["work"], status=status
            )


def test_execution_needs_reference_date_and_permission(workspace, review):
    w = workspace
    services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    for date, note in [(None, ""), (timezone.now() + timedelta(days=1), "Future")]:
        with pytest.raises(ValidationError):
            services.change_status(
                actor=w["staff"],
                organization=w["org"],
                work=w["work"],
                status="completed",
                executed_at=date,
                execution_note=note,
            )
    profile = make_staff_member(
        email="email-editor@example.com",
        roles=[make_role("Email editor", ["email_marketing_edit"])],
    )
    assign_client(profile, w["org"])
    with pytest.raises(PermissionDenied):
        services.change_status(
            actor=profile.user,
            organization=w["org"],
            work=w["work"],
            status="completed",
            executed_at=timezone.now(),
            execution_note="External report",
        )


def test_only_flow_can_be_active_and_completion_preserves_start(workspace):
    w = workspace
    work = services.save_work(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        name="Welcome sequence",
        kind="automation",
        trigger_description="Account created → welcome",
    )
    start = timezone.now() - timedelta(days=2)
    active = services.change_status(
        actor=w["staff"],
        organization=w["org"],
        work=work,
        status="active",
        executed_at=start,
        execution_note="Activated externally",
    )
    complete = services.change_status(
        actor=w["staff"], organization=w["org"], work=active, status="completed"
    )
    assert complete.executed_at == start
    assert complete.execution_note == "Activated externally"
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"], organization=w["org"], work=complete, status="draft"
        )


def test_campaign_cannot_use_active_flow_status(workspace):
    w = workspace
    work = services.save_work(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        name="Campaign",
        kind="campaign",
    )
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"],
            organization=w["org"],
            work=work,
            status="active",
            executed_at=timezone.now(),
            execution_note="External report",
        )


def test_executed_work_preserved_but_report_summary_editable(workspace, executed):
    w = workspace
    with pytest.raises(ValidationError):
        services.save_work(
            actor=w["staff"],
            organization=w["org"],
            work=executed,
            expected_revision=1,
            subject="Rewrite",
        )
    with pytest.raises(ValidationError):
        services.save_deliverable(
            actor=w["staff"], organization=w["org"], work=executed, name="New proof"
        )
    result = services.save_work(
        actor=w["staff"],
        organization=w["org"],
        work=executed,
        expected_revision=1,
        result_summary="Three conversions observed",
        internal_notes="Staff only",
    )
    assert result.result_summary == "Three conversions observed"
    assert result.revision == 1


def test_daily_results_replace_a_date_and_filter_correctly(workspace, executed):
    w = workspace
    today = timezone.localdate()
    args = {
        "actor": w["staff"],
        "organization": w["org"],
        "work": executed,
        "source": "External daily report",
    }
    services.record_metrics(**args, date=today, **dict.fromkeys(METRICS, 2))
    services.record_metrics(**args, date=today - timedelta(days=1), **dict.fromkeys(METRICS, 3))
    services.record_metrics(**args, date=today, **dict.fromkeys(METRICS, 4))
    assert EmailMetric.objects.count() == 2
    assert selectors.workspace(w["user"], w["org"], {})["totals"]["opens"] == 7
    assert (
        selectors.workspace(w["user"], w["org"], {"start": today, "end": today})["totals"]["opens"]
        == 4
    )
    assert (
        selectors.workspace(w["user"], w["org"], {"kind": "automation"})["totals"]["opens"] is None
    )


@pytest.mark.parametrize("value", [-1, 0.1, Decimal("NaN"), "Infinity"])
def test_invalid_metrics_and_audience_rejected(workspace, executed, value):
    w = workspace
    with pytest.raises(ValidationError):
        services.save_work(
            actor=w["staff"],
            organization=w["org"],
            campaign=w["campaign"],
            name="Invalid",
            kind="newsletter",
            audience_size=value,
        )
    with pytest.raises(ValidationError):
        services.record_metrics(
            actor=w["staff"],
            organization=w["org"],
            work=executed,
            date=timezone.localdate(),
            source="Report",
            **dict.fromkeys(METRICS, value),
        )


@pytest.mark.parametrize("days", [-10, 1])
def test_observation_dates_validated(workspace, executed, days):
    w = workspace
    with pytest.raises(ValidationError):
        services.record_metrics(
            actor=w["staff"],
            organization=w["org"],
            work=executed,
            date=timezone.localdate() + timedelta(days=days),
            source="Report",
            **dict.fromkeys(METRICS, 0),
        )


def test_correction_requires_edit_access(workspace, executed):
    w = workspace
    profile = make_staff_member(
        email="email-recorder@example.com",
        roles=[make_role("Email recorder", ["email_marketing_create"])],
    )
    assign_client(profile, w["org"])
    args = {
        "actor": profile.user,
        "organization": w["org"],
        "work": executed,
        "date": timezone.localdate(),
        "source": "Report",
        **dict.fromkeys(METRICS, 0),
    }
    services.record_metrics(**args)
    with pytest.raises(PermissionDenied):
        services.record_metrics(**args)


def test_cancel_closes_pending_reviews(workspace, review):
    w = workspace
    services.change_status(
        actor=w["staff"], organization=w["org"], work=w["work"], status="cancelled"
    )
    review.refresh_from_db()
    assert review.status == "cancelled"
    with pytest.raises(ValidationError):
        services.change_status(
            actor=w["staff"], organization=w["org"], work=w["work"], status="draft"
        )


def test_no_observations_are_not_fabricated_zeroes(workspace):
    w = workspace
    assert selectors.workspace(w["user"], w["org"], {})["totals"]["opens"] is None


@pytest.mark.parametrize("kind", ["campaign", "newsletter", "automation"])
def test_entire_email_workflow_sends_nothing(
    workspace, monkeypatch, mailoutbox, django_capture_on_commit_callbacks, kind
):
    from django.core.mail import EmailMessage

    w = workspace

    def forbidden(*args, **kwargs):
        pytest.fail("Email Marketing must never send a message")

    monkeypatch.setattr(EmailMessage, "send", forbidden)
    mailoutbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        services.save_work(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            expected_revision=1,
            kind=kind,
        )
        review = services.request_review(
            actor=w["staff"], organization=w["org"], deliverable=w["delivery"]
        )
        services.decide_review(
            actor=w["user"], organization=w["org"], approval=review, decision="approved"
        )
        scheduled = services.change_status(
            actor=w["staff"], organization=w["org"], work=w["work"], status="scheduled"
        )
        assert scheduled.executed_at is None
        if kind == "automation":
            services.change_status(
                actor=w["staff"],
                organization=w["org"],
                work=w["work"],
                status="active",
                executed_at=timezone.now(),
                execution_note="Flow in external tool",
            )
        executed = services.change_status(
            actor=w["staff"],
            organization=w["org"],
            work=w["work"],
            status="completed",
            executed_at=timezone.now(),
            execution_note="External execution",
        )
        services.record_metrics(
            actor=w["staff"],
            organization=w["org"],
            work=executed,
            date=timezone.localdate(),
            source="External report",
            **dict.fromkeys(METRICS, 0),
        )
    assert mailoutbox == []
    assert EmailWorkItem.objects.count() == 1
