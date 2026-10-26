from datetime import timedelta

import pytest
from django.utils import timezone

from apps.campaigns.tests.factories import make_campaign
from apps.organizations.tests.factories import make_tenant
from apps.social import services
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
    org, user = make_tenant("Social client")
    campaign = make_campaign(org, actor=admin, name="Brand storytelling", service_type="social")
    profile = make_staff_member(
        roles=[
            make_role(
                "Social operator", ["social_view", "social_create", "social_edit", "social_publish"]
            )
        ]
    )
    assign_client(profile, org)
    subscription = make_subscription(
        org,
        actor=admin,
        service=make_service(
            "Social service", category_slug="social-tests", workspace_module="social"
        ),
    )
    channel = services.save_channel(
        actor=profile.user, organization=org, name="Brand Instagram", platform="instagram"
    )
    content = services.save_content(
        actor=profile.user,
        organization=org,
        campaign=campaign,
        channel=channel,
        title="Launch reel",
        kind="reel",
        caption="Our new collection",
        client_visible=True,
        scheduled_at=timezone.now() + timedelta(days=2),
    )
    delivery = services.save_deliverable(
        actor=profile.user,
        organization=org,
        content=content,
        title="Final edit",
        description="Thirty second launch video",
        asset_url="https://example.com/review",
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
        "channel": channel,
        "content": content,
        "delivery": delivery,
    }


@pytest.fixture
def review(workspace):
    return services.request_review(
        actor=workspace["staff"], organization=workspace["org"], deliverable=workspace["delivery"]
    )


@pytest.fixture
def published(workspace, review):
    services.decide_review(
        actor=workspace["user"], organization=workspace["org"], approval=review, decision="approved"
    )
    return services.change_status(
        actor=workspace["staff"],
        organization=workspace["org"],
        content=workspace["content"],
        status="published",
        published_at=timezone.now() - timedelta(days=3),
        published_url="https://example.com/post",
    )
