import importlib

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone

from apps.approvals import services
from apps.approvals.models import ApprovalRequest
from apps.email_marketing import services as email
from apps.notifications.models import Notification
from apps.social import services as social
from apps.social.models import SocialApproval

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("domain", ["social", "email_marketing"])
@pytest.mark.parametrize("decision", ["approved", "changes_requested", "rejected"])
def test_shared_decision_updates_domain_review(
    workspace, social_work, email_work, domain, decision
):
    w = workspace
    source, (_, delivery) = (social, social_work) if domain == "social" else (email, email_work)
    review = source.request_review(actor=w["staff"], organization=w["org"], deliverable=delivery)
    request = review.approval_request
    services.decide(
        actor=w["user"],
        organization=w["org"],
        request=request,
        decision=decision,
        response="Review response",
    )
    review.refresh_from_db()
    assert review.status == decision
    assert review.feedback == "Review response"
    assert review.decided_by == w["user"]
    assert request.history.count() == 2


@pytest.mark.parametrize("domain", ["social", "email_marketing"])
def test_old_decision_entry_point_uses_shared_workflow(workspace, social_work, email_work, domain):
    w = workspace
    source, (_, delivery) = (social, social_work) if domain == "social" else (email, email_work)
    review = source.request_review(actor=w["staff"], organization=w["org"], deliverable=delivery)
    source.decide_review(
        actor=w["user"],
        organization=w["org"],
        approval=review,
        decision="rejected",
        feedback="Not suitable",
    )
    request = ApprovalRequest.objects.get(pk=review.approval_request.pk)
    assert request.status == "rejected"
    assert request.history.latest("pk").kind == "decided"


@pytest.mark.parametrize("domain", ["social", "email_marketing"])
@pytest.mark.parametrize("change", ["parent", "delivery", "cancel"])
def test_source_invalidation_records_shared_history(
    workspace, social_work, email_work, domain, change
):
    w = workspace
    source, (parent, delivery) = (
        (social, social_work) if domain == "social" else (email, email_work)
    )
    review = source.request_review(actor=w["staff"], organization=w["org"], deliverable=delivery)
    kwargs = {
        "actor": w["staff"],
        "organization": w["org"],
        "content" if domain == "social" else "work": parent,
    }
    if change == "parent":
        save = social.save_content if domain == "social" else email.save_work
        save(
            **kwargs,
            expected_revision=1,
            **{"caption" if domain == "social" else "subject": "New copy"},
        )
    elif change == "delivery":
        source.save_deliverable(
            **kwargs, deliverable=delivery, expected_revision=1, description="New draft"
        )
    else:
        source.change_status(**kwargs, status="cancelled")
    request = ApprovalRequest.objects.get(pk=review.approval_request.pk)
    assert request.status == "cancelled"
    assert request.history.latest("pk").kind == "cancelled"
    assert request.resolved_at
    with pytest.raises(ValidationError):
        services.decide(
            actor=w["user"], organization=w["org"], request=request, decision="approved"
        )


def test_shared_rejection_blocks_publication(workspace, social_work):
    w = workspace
    content, delivery = social_work
    review = social.request_review(actor=w["staff"], organization=w["org"], deliverable=delivery)
    services.decide(
        actor=w["user"],
        organization=w["org"],
        request=review.approval_request,
        decision="rejected",
        response="Wrong direction",
    )
    with pytest.raises(ValidationError):
        social.change_status(
            actor=w["staff"],
            organization=w["org"],
            content=content,
            status="published",
            published_at=timezone.now(),
            published_url="https://example.com/post",
        )


def test_migration_preserves_legacy_reviews_without_notifications(workspace, social_work):
    from types import SimpleNamespace

    w = workspace
    content, delivery = social_work
    rows = []
    for status in ["pending", "approved", "changes_requested", "cancelled"]:
        rows.append(
            SocialApproval.objects.create(
                organization=w["org"],
                deliverable=delivery,
                deliverable_revision=1,
                content_revision=content.revision,
                requested_by=w["staff"],
                decided_by=w["user"] if status in {"approved", "changes_requested"} else None,
                decided_at=timezone.now() if status in {"approved", "changes_requested"} else None,
                status=status,
                snapshot={"title": "Original preview", "description": "Original text"},
                feedback="Legacy response" if status == "changes_requested" else "",
            )
        )
    count = Notification.objects.count()
    migrate = importlib.import_module(
        "apps.approvals.migrations.0002_import_delivery_reviews"
    ).import_reviews
    migrate(apps, SimpleNamespace(connection=connection))
    migrate(apps, SimpleNamespace(connection=connection))
    assert ApprovalRequest.objects.count() == 4
    for row in rows:
        request = ApprovalRequest.objects.get(social_review=row)
        assert request.title == "Original preview"
        assert request.requested_at == row.created_at
        assert request.status == row.status
        assert request.history.count() == (1 if row.status == "pending" else 2)
        assert bool(request.resolved_at) == (row.status != "pending")
    assert Notification.objects.count() == count
