import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.approvals import selectors, services
from apps.approvals.models import ApprovalComment, ApprovalHistory, ApprovalRequest
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_request_has_history_and_in_app_notification(workspace, approval):
    w = workspace
    assert approval.requested_by == w["staff"]
    assert approval.requested_at
    assert approval.resolved_at is None
    assert approval.history.get().to_status == "pending"
    assert Notification.objects.filter(recipient=w["user"], category="approval").exists()
    assert selectors.pending_for(w["user"], w["org"]).get() == approval


@pytest.mark.parametrize("decision", ["approved", "changes_requested", "rejected"])
def test_decisions_resolve_and_record_history_and_notifications(workspace, approval, decision):
    w = workspace
    Notification.objects.filter(category="approval").delete()
    result = services.decide(
        actor=w["user"],
        organization=w["org"],
        request=approval,
        decision=decision,
        response="Client explanation",
    )
    assert result.status == decision
    assert result.resolved_at
    assert result.resolved_by == w["user"]
    assert result.client_response == "Client explanation"
    event = result.history.latest("pk")
    assert (event.from_status, event.to_status, event.actor) == ("pending", decision, w["user"])
    assert Notification.objects.filter(recipient=w["staff"], category="approval").exists()
    assert not selectors.pending_for(w["user"], w["org"]).exists()
    count = Notification.objects.count()
    with pytest.raises(ValidationError):
        services.decide(
            actor=w["user"], organization=w["org"], request=approval, decision="approved"
        )
    assert Notification.objects.count() == count
    assert result.history.count() == 2


@pytest.mark.parametrize("decision", ["changes_requested", "rejected", "cancelled", "anything"])
def test_invalid_or_unexplained_client_decision_rejected(workspace, approval, decision):
    w = workspace
    with pytest.raises(ValidationError):
        services.decide(actor=w["user"], organization=w["org"], request=approval, decision=decision)
    approval.refresh_from_db()
    assert approval.status == "pending"
    assert approval.history.count() == 1


def test_comments_do_not_resolve_and_can_continue_after_decision(workspace, approval):
    w = workspace
    for actor in [w["user"], w["staff"]]:
        comment = services.add_comment(
            actor=actor, organization=w["org"], request=approval, body="A shared question"
        )
        assert comment.author == actor
        assert ApprovalHistory.objects.get(comment=comment).kind == "commented"
    approval.refresh_from_db()
    assert approval.status == "pending"
    services.decide(actor=w["user"], organization=w["org"], request=approval, decision="approved")
    services.add_comment(
        actor=w["staff"], organization=w["org"], request=approval, body="Thanks, recorded."
    )
    assert approval.comments.count() == 3
    assert approval.history.count() == 5


@pytest.mark.parametrize("body", ["", "  ", "x" * 5001], ids=["empty", "whitespace", "too-long"])
def test_invalid_comment_creates_no_history(workspace, approval, body):
    w = workspace
    count = Notification.objects.count()
    with pytest.raises(ValidationError):
        services.add_comment(actor=w["user"], organization=w["org"], request=approval, body=body)
    assert not ApprovalComment.objects.exists()
    assert approval.history.count() == 1
    assert Notification.objects.count() == count


def test_staff_can_cancel_with_reason_but_cannot_make_client_decision(workspace, approval):
    w = workspace
    with pytest.raises(PermissionDenied):
        services.decide(
            actor=w["admin"], organization=w["org"], request=approval, decision="approved"
        )
    result = services.cancel(
        actor=w["staff"], organization=w["org"], request=approval, reason="Work superseded"
    )
    assert result.status == "cancelled"
    assert result.history.latest("pk").detail == "Work superseded"
    with pytest.raises(ValidationError):
        services.decide(
            actor=w["user"], organization=w["org"], request=approval, decision="approved"
        )


def test_resolved_request_cannot_be_cancelled(workspace, approval):
    w = workspace
    services.decide(actor=w["user"], organization=w["org"], request=approval, decision="approved")
    with pytest.raises(ValidationError):
        services.cancel(
            actor=w["staff"], organization=w["org"], request=approval, reason="Too late"
        )


def test_notifications_history_and_decision_roll_back_together(workspace, approval, monkeypatch):
    w = workspace
    from apps.approvals import notifications

    def fail(*args, **kwargs):
        raise RuntimeError("Notification write failed")

    monkeypatch.setattr(notifications, "changed", fail)
    with pytest.raises(RuntimeError), transaction.atomic():
        services.decide(
            actor=w["user"], organization=w["org"], request=approval, decision="approved"
        )
    approval.refresh_from_db()
    assert approval.status == "pending"
    assert approval.history.count() == 1


def test_workflow_sends_no_mail(
    workspace, monkeypatch, mailoutbox, django_capture_on_commit_callbacks
):
    from django.core.mail import EmailMessage

    w = workspace

    def forbidden(*args, **kwargs):
        pytest.fail("Approvals must not send email")

    monkeypatch.setattr(EmailMessage, "send", forbidden)
    mailoutbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        request = services.create_request(
            actor=w["staff"], organization=w["org"], campaign=w["campaign"], title="Approve"
        )
        services.add_comment(
            actor=w["user"], organization=w["org"], request=request, body="Please clarify"
        )
        services.decide(
            actor=w["user"],
            organization=w["org"],
            request=request,
            decision="rejected",
            response="Scope is wrong",
        )
    assert mailoutbox == []
    assert Notification.objects.filter(category="approval").exists()


def test_request_validates_campaign_organization(workspace):
    from apps.organizations.tests.factories import make_tenant

    w = workspace
    other, _ = make_tenant("Different client")
    with pytest.raises(ValidationError):
        services.create_request(
            actor=w["admin"], organization=other, campaign=w["campaign"], title="Wrong campaign"
        )
    assert not ApprovalRequest.objects.exists()
