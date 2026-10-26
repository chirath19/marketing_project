"""Test helpers for staff, roles and assignments."""

from __future__ import annotations

from django.contrib.auth.models import Permission

from apps.accounts.models import AccountStatus, UserType
from apps.accounts.tests.factories import PASSWORD, make_user
from apps.organizations.tests.factories import make_org
from apps.permissions.catalogue import catalogue_filter
from apps.permissions.models import Role, RolePermission
from apps.staff.models import AssignmentRole, StaffClientAssignment, StaffProfile

__all__ = [
    "PASSWORD", "make_org", "make_role", "make_staff_member",
    "make_super_admin_user", "assign_client",
]


def make_role(name: str, codenames: list[str]) -> Role:
    """A role holding exactly these permissions.

    `get_or_create`, because the seed migration ships system roles and a
    test naming one of them should configure that role rather than fail on
    the unique constraint.
    """
    role, _created = Role.objects.get_or_create(
        name=name, defaults={"slug": name.lower().replace(" ", "-")},
    )

    RolePermission.objects.filter(role=role).delete()
    permissions = Permission.objects.filter(**catalogue_filter(),
                                            codename__in=codenames)
    RolePermission.objects.bulk_create(
        [RolePermission(role=role, permission=permission)
         for permission in permissions]
    )
    return role


def make_staff_member(email: str = "specialist@heliograph.agency", *,
                      roles: list[Role] | None = None,
                      has_all_client_access: bool = False,
                      status: str = AccountStatus.ACTIVE) -> StaffProfile:
    user = make_user(email=email, user_type=UserType.STAFF, status=status)
    profile = StaffProfile.objects.create(
        user=user, has_all_client_access=has_all_client_access,
    )
    if roles:
        profile.roles.set(roles)
    return profile


def make_super_admin_user(email: str = "root@heliograph.agency"):  # noqa: ANN201
    """A super admin as `create_staff_account` actually makes one.

    `is_superuser` and `is_staff` are set too, because the service sets
    them: the platform's own authorisation reads `user_type`, while
    Django's model permissions and the admin read these flags. A fixture
    that set only one would test a user the product never creates.
    """
    user = make_user(
        email=email, user_type=UserType.SUPER_ADMIN,
        is_superuser=True, is_staff=True,
    )
    StaffProfile.objects.create(user=user, has_all_client_access=True)
    return user


def assign_client(profile: StaffProfile, organization, *,
                  role: str = AssignmentRole.SPECIALIST) -> StaffClientAssignment:
    return StaffClientAssignment.objects.create(
        staff=profile, organization=organization, role=role,
    )
