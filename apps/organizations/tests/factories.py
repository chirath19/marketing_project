"""Test helpers for organization fixtures."""

from __future__ import annotations

from apps.accounts.models import AccountStatus, UserType
from apps.accounts.tests.factories import PASSWORD, make_user
from apps.organizations.models import (
    MemberRole,
    MemberStatus,
    Organization,
    OrganizationMember,
    OrganizationStatus,
)

__all__ = ["PASSWORD", "make_user", "make_org", "make_member", "make_tenant"]


def make_org(name: str = "ABC Holdings", *, status: str = OrganizationStatus.ACTIVE,
             **extra) -> Organization:
    return Organization.objects.create(
        name=name,
        slug=Organization.build_slug(
            name, taken=set(Organization.objects.values_list("slug", flat=True))
        ),
        status=status,
        **extra,
    )


def make_member(organization: Organization, user, *, role: str = MemberRole.MEMBER,
                status: str = MemberStatus.ACTIVE) -> OrganizationMember:
    return OrganizationMember.objects.create(
        organization=organization, user=user, role=role, status=status,
    )


def make_tenant(name: str, *, owner_email: str | None = None,
                account_status: str = AccountStatus.ACTIVE,
                org_status: str = OrganizationStatus.ACTIVE):
    """A complete client: an organization with an owner who can sign in.

    Returns ``(organization, owner)``.
    """
    organization = make_org(name, status=org_status)
    email = owner_email or f"owner@{organization.slug}.example"
    owner = make_user(email=email, status=account_status, user_type=UserType.CLIENT)
    make_member(organization, owner, role=MemberRole.OWNER)
    return organization, owner
