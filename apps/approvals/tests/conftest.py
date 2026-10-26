import pytest

from apps.approvals import services
from apps.campaigns.tests.factories import make_campaign
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
    org, user = make_tenant("Approvals client")
    campaign = make_campaign(org, actor=admin, name="Client launch", service_type="social")
    profile = make_staff_member(
        roles=[
            make_role(
                "Approval operator",
                [
                    "approvals_view",
                    "approvals_create",
                    "approvals_approve",
                    "social_view",
                    "social_create",
                    "social_edit",
                    "social_publish",
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
            "Social service", category_slug="approval-social", workspace_module="social"
        ),
    )
    return {
        "admin": admin,
        "org": org,
        "user": user,
        "campaign": campaign,
        "staff": profile.user,
        "profile": profile,
        "subscription": subscription,
    }


@pytest.fixture
def approval(workspace):
    w = workspace
    return services.create_request(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        title="Approve the launch brief",
        description="Review the proposed launch direction.",
    )


@pytest.fixture
def social_work(workspace):
    from apps.social import services as social

    w = workspace
    channel = social.save_channel(
        actor=w["staff"], organization=w["org"], name="Client social", platform="instagram"
    )
    content = social.save_content(
        actor=w["staff"],
        organization=w["org"],
        campaign=w["campaign"],
        channel=channel,
        title="Launch reel",
        caption="Version one",
        client_visible=True,
    )
    delivery = social.save_deliverable(
        actor=w["staff"],
        organization=w["org"],
        content=content,
        title="Reel preview",
        description="Review the reel",
        client_visible=True,
    )
    return content, delivery


@pytest.fixture
def email_work(workspace):
    from apps.email_marketing import services as email

    w = workspace
    campaign = make_campaign(
        w["org"], actor=w["admin"], name="Retention", service_type="email_marketing"
    )
    make_subscription(
        w["org"],
        actor=w["admin"],
        service=make_service(
            "Email service", category_slug="approval-email", workspace_module="email_marketing"
        ),
    )
    work = email.save_work(
        actor=w["staff"],
        organization=w["org"],
        campaign=campaign,
        name="Newsletter",
        kind="newsletter",
        subject="First subject",
        client_visible=True,
    )
    delivery = email.save_deliverable(
        actor=w["staff"],
        organization=w["org"],
        work=work,
        name="Newsletter proof",
        description="Review newsletter",
        client_visible=True,
    )
    return work, delivery
