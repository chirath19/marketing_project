from datetime import timedelta

import pytest
from django.utils import timezone

from apps.campaigns.tests.factories import make_campaign
from apps.email_marketing import services
from apps.organizations.tests.factories import make_tenant
from apps.staff.tests.factories import (
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)
from apps.subscriptions.tests.factories import make_service, make_subscription


@pytest.fixture
def workspace():
    admin = make_super_admin_user()
    org, user = make_tenant("Email client")
    campaign = make_campaign(
        org, actor=admin, name="Retention service", service_type="email_marketing"
    )
    profile = make_staff_member(
        roles=[
            make_role(
                "Email operator",
                [
                    "email_marketing_view",
                    "email_marketing_create",
                    "email_marketing_edit",
                    "email_marketing_publish",
                ],
            )
        ]
    )
    assign_client(profile, org)
    subscription = make_subscription(
        org,
        actor=admin,
        service=make_service(
            "Email service", category_slug="email-test", workspace_module="email_marketing"
        ),
    )
    work = services.save_work(
        actor=profile.user,
        organization=org,
        campaign=campaign,
        name="October newsletter",
        kind="newsletter",
        subject="October update",
        brief="Original copy",
        audience_size=200,
        scheduled_at=timezone.now() + timedelta(days=2),
        client_visible=True,
    )
    delivery = services.save_deliverable(
        actor=profile.user,
        organization=org,
        work=work,
        name="Newsletter proof",
        description="Review the newsletter copy and layout",
        asset_url="https://example.com/preview/v1",
        client_visible=True,
    )
    return {
        "admin": admin,
        "org": org,
        "user": user,
        "campaign": campaign,
        "staff": profile.user,
        "profile": profile,
        "subscription": subscription,
        "work": work,
        "delivery": delivery,
    }


@pytest.fixture
def review(workspace):
    return services.request_review(
        actor=workspace["staff"], organization=workspace["org"], deliverable=workspace["delivery"]
    )


@pytest.fixture
def executed(workspace, review):
    w = workspace
    services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    return services.change_status(
        actor=w["staff"],
        organization=w["org"],
        work=w["work"],
        status="completed",
        executed_at=timezone.now() - timedelta(days=3),
        execution_note="External report 123",
    )
