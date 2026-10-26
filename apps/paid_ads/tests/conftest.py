from datetime import date
from decimal import Decimal

import pytest

from apps.campaigns.tests.factories import make_campaign
from apps.organizations.tests.factories import make_tenant
from apps.paid_ads import services
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
    org, user = make_tenant("Ads client")
    campaign = make_campaign(org, actor=admin, name="Search acquisition")
    profile = make_staff_member(
        roles=[
            make_role(
                "Ads test",
                [
                    "paid_ads_view",
                    "paid_ads_create",
                    "paid_ads_edit",
                ],
            )
        ]
    )
    assign_client(profile, org)
    subscription = make_subscription(
        org,
        actor=admin,
        service=make_service(
            "Paid service", category_slug="paid-test", workspace_module="paid_ads"
        ),
    )
    return {
        "admin": admin,
        "org": org,
        "user": user,
        "campaign": campaign,
        "staff": profile.user,
        "subscription": subscription,
    }


@pytest.fixture
def record(workspace):
    def create(**overrides):
        values = {
            "organization": workspace["org"],
            "campaign": workspace["campaign"],
            "actor": workspace["staff"],
            "date": date(2026, 1, 1),
            "platform": "google",
            "source": "Uploaded platform report",
            "spend": Decimal("100"),
            "impressions": 1000,
            "clicks": 100,
            "leads": 10,
            "conversions": 5,
            "revenue": Decimal("400"),
        }
        values.update(overrides)
        return services.record_metrics(**values)

    return create


@pytest.fixture
def filters():
    return {
        "start": date(2026, 1, 1),
        "end": date(2026, 1, 31),
        "currency": "USD",
        "platform": "",
        "campaign": None,
    }
