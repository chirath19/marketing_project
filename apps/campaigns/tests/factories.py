"""Test helpers for campaigns."""

from __future__ import annotations

from apps.campaigns.models import Campaign, CampaignStatus

__all__ = ["make_campaign"]


def make_campaign(organization, *, actor=None, name: str = "Spring push",  # noqa: ANN001
                  service_type: str = "paid_ads",
                  status: str = CampaignStatus.PLANNED,
                  **fields) -> Campaign:
    """A campaign, built the way the real one is.

    Through the service layer rather than `objects.create`, so a test
    exercises the same path staff do — a row made directly would skip
    the history entry and the started-at stamp, and would quietly prove
    less than it appears to.
    """
    from apps.campaigns.services import create_campaign
    from apps.staff.tests.factories import make_super_admin_user

    if actor is None:
        actor = make_super_admin_user("campaign-setup@heliograph.agency")

    return create_campaign(
        organization=organization, name=name, actor=actor,
        service_type=service_type, status=status, **fields,
    )
