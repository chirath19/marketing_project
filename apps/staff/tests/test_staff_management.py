"""Staff management: what a super admin can do, and what nobody can."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import AccountStatus, UserType
from apps.organizations.tests.factories import make_org
from apps.permissions import services as permission_services
from apps.permissions.models import OverrideEffect, Role
from apps.staff import selectors, services
from apps.staff.models import AssignmentRole, AssignmentStatus, StaffProfile
from apps.staff.tests.factories import (
    PASSWORD,
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def super_admin():
    return make_super_admin_user()


# --- creating staff ---------------------------------------------------------


def test_a_super_admin_creates_a_staff_account(super_admin):
    profile = services.create_staff_account(
        email="New.Person@heliograph.agency", full_name="New Person",
        password=PASSWORD, job_title="SEO Specialist", actor=super_admin,
    )

    assert profile.user.email == "new.person@heliograph.agency"
    assert profile.user.user_type == UserType.STAFF
    assert profile.user.status == AccountStatus.ACTIVE, "staff start usable"
    assert profile.user.check_password(PASSWORD)


def test_a_new_staff_account_has_no_django_admin_access_by_default(super_admin):
    """The Staff user type is the staff dashboard; `is_staff` is the Django
    admin. Conflating them would hand the admin to every account manager."""
    profile = services.create_staff_account(
        email="person@heliograph.agency", password=PASSWORD, actor=super_admin,
    )

    assert profile.user.is_staff_member
    assert not profile.user.is_staff


def test_creating_a_super_admin_requires_being_one():
    manager = make_staff_member(
        "ops@heliograph.agency", roles=[make_role("Ops", ["staff_manage"])],
    )

    with pytest.raises(PermissionDenied, match="super admin"):
        services.create_staff_account(
            email="escalate@heliograph.agency", password=PASSWORD,
            is_super_admin=True, actor=manager.user,
        )


def test_an_operations_manager_can_create_ordinary_staff():
    manager = make_staff_member(
        "ops@heliograph.agency", roles=[make_role("Ops", ["staff_manage"])],
    )

    profile = services.create_staff_account(
        email="new@heliograph.agency", password=PASSWORD, actor=manager.user,
    )

    assert profile.pk


def test_a_duplicate_email_is_refused(super_admin):
    services.create_staff_account(email="dup@heliograph.agency",
                                  password=PASSWORD, actor=super_admin)

    with pytest.raises(services.StaffError, match="already exists"):
        services.create_staff_account(email="DUP@heliograph.agency",
                                      password=PASSWORD, actor=super_admin)


def test_creating_staff_needs_the_manage_permission():
    specialist = make_staff_member(roles=[make_role("SEO only", ["seo_edit"])])

    with pytest.raises(PermissionDenied):
        services.create_staff_account(email="x@heliograph.agency",
                                      password=PASSWORD, actor=specialist.user)


# --- editing and deactivating ----------------------------------------------


def test_a_super_admin_edits_a_staff_profile(super_admin):
    profile = make_staff_member()

    services.update_staff(profile=profile, actor=super_admin,
                          job_title="Lead SEO", department="Delivery")
    profile.refresh_from_db()

    assert profile.job_title == "Lead SEO"


def test_only_a_super_admin_grants_access_to_every_client():
    """It is the one switch that makes assignments stop mattering."""
    manager = make_staff_member(
        "ops@heliograph.agency", roles=[make_role("Ops", ["staff_manage"])],
    )
    profile = make_staff_member("other@heliograph.agency")

    with pytest.raises(PermissionDenied, match="every client"):
        services.update_staff(profile=profile, actor=manager.user,
                              has_all_client_access=True)


def test_a_field_outside_the_service_is_refused(super_admin):
    profile = make_staff_member()

    with pytest.raises(ValidationError):
        services.update_staff(profile=profile, actor=super_admin,
                              user_id=super_admin.pk)


def test_deactivating_stops_sign_in_and_reactivating_restores_it(super_admin, client):
    profile = make_staff_member()

    services.deactivate_staff(profile=profile, actor=super_admin, reason="On leave")
    profile.user.refresh_from_db()
    assert profile.user.status == AccountStatus.SUSPENDED
    assert not client.login(username=profile.user.email, password=PASSWORD)

    services.activate_staff(profile=profile, actor=super_admin, reason="Back")
    profile.user.refresh_from_db()
    assert profile.user.status == AccountStatus.ACTIVE
    assert client.login(username=profile.user.email, password=PASSWORD)


def test_a_deactivated_staff_account_is_kept_not_deleted(super_admin):
    profile = make_staff_member()
    services.deactivate_staff(profile=profile, actor=super_admin)

    assert StaffProfile.objects.filter(pk=profile.pk).exists()


# --- roles ------------------------------------------------------------------


def test_assigning_roles_replaces_rather_than_adds(super_admin):
    first = make_role("First", ["seo_view"])
    second = make_role("Second", ["paid_ads_view"])
    profile = make_staff_member(roles=[first])

    services.assign_roles(profile=profile, roles=[second], actor=super_admin)

    assert list(profile.roles.all()) == [second]


def test_assigning_roles_takes_effect_immediately(super_admin):
    """The resolved permissions are cached per request; the service clears
    the cache so a change is not one request late."""
    from apps.permissions import access

    role = make_role("SEO", ["seo_edit"])
    profile = make_staff_member()
    assert not access.has_permission(profile.user, "permissions.seo_edit")

    services.assign_roles(profile=profile, roles=[role], actor=super_admin)

    assert access.has_permission(profile.user, "permissions.seo_edit")


def test_assigning_roles_needs_the_assign_permission():
    specialist = make_staff_member(roles=[make_role("SEO only", ["seo_edit"])])
    other = make_staff_member("other@heliograph.agency")

    with pytest.raises(PermissionDenied):
        services.assign_roles(profile=other, roles=[], actor=specialist.user)


# --- role configuration -----------------------------------------------------


def test_a_super_admin_creates_a_role(super_admin):
    role = permission_services.create_role(
        name="Outreach", actor=super_admin,
        permissions=["seo_view", "seo_edit"],
    )

    assert role.permission_codenames == {"seo_view", "seo_edit"}


def test_setting_permissions_removes_the_ones_left_out(super_admin):
    """A configuration screen posts the ticked boxes, so unticking one has
    to remove it."""
    role = make_role("Outreach", ["seo_view", "seo_edit", "seo_delete"])

    permission_services.set_role_permissions(
        role=role, codenames=["seo_view"], actor=super_admin,
    )

    assert role.permission_codenames == {"seo_view"}


def test_an_unknown_permission_is_refused(super_admin):
    """A typo must not silently produce a role with fewer rights than
    whoever configured it believed."""
    role = make_role("Outreach", ["seo_view"])

    with pytest.raises(ValidationError, match="Unknown permission"):
        permission_services.set_role_permissions(
            role=role, codenames=["seo_edit", "seo_teleport"], actor=super_admin,
        )
    assert role.permission_codenames == {"seo_view"}


def test_a_duplicate_role_name_is_refused(super_admin):
    permission_services.create_role(name="Outreach", actor=super_admin)

    with pytest.raises(ValidationError, match="already exists"):
        permission_services.create_role(name="outreach", actor=super_admin)


def test_a_system_role_cannot_be_deleted(super_admin):
    role = Role.objects.filter(is_system=True).first()
    assert role is not None

    with pytest.raises(ValidationError, match="cannot be deleted"):
        permission_services.delete_role(role=role, actor=super_admin)


def test_a_custom_role_can_be_deleted(super_admin):
    role = permission_services.create_role(name="Temporary", actor=super_admin)

    permission_services.delete_role(role=role, actor=super_admin)

    assert not Role.objects.filter(name="Temporary").exists()


def test_managing_roles_needs_the_permission():
    specialist = make_staff_member(roles=[make_role("SEO only", ["seo_edit"])])

    with pytest.raises(PermissionDenied):
        permission_services.create_role(name="Escalation", actor=specialist.user)


# --- overrides --------------------------------------------------------------


def test_a_super_admin_grants_a_personal_exception(super_admin):
    profile = make_staff_member(roles=[make_role("SEO", ["seo_view"])])

    permission_services.set_override(
        user=profile.user, permission_codename="analytics_export",
        effect=OverrideEffect.GRANT, actor=super_admin, reason="Builds the board pack",
    )

    assert profile.user.has_perm("permissions.analytics_export")


def test_a_super_admin_withholds_a_permission_a_role_grants(super_admin):
    profile = make_staff_member(roles=[make_role("SEO", ["seo_view", "seo_edit"])])

    permission_services.set_override(
        user=profile.user, permission_codename="seo_edit",
        effect=OverrideEffect.DENY, actor=super_admin, reason="Under investigation",
    )

    assert not profile.user.has_perm("permissions.seo_edit")
    assert profile.user.has_perm("permissions.seo_view")


def test_an_override_replaces_the_previous_one(super_admin):
    from apps.permissions.models import UserPermissionOverride

    profile = make_staff_member()
    for effect in (OverrideEffect.GRANT, OverrideEffect.DENY, OverrideEffect.GRANT):
        permission_services.set_override(
            user=profile.user, permission_codename="seo_edit",
            effect=effect, actor=super_admin,
        )

    assert UserPermissionOverride.objects.filter(user=profile.user).count() == 1
    assert profile.user.has_perm("permissions.seo_edit")


def test_only_a_super_admin_manages_overrides():
    """An override beats every role, so delegating it through a role would
    make the hierarchy circular."""
    manager = make_staff_member(
        "ops@heliograph.agency",
        roles=[make_role("Ops", ["staff_manage", "roles_manage"])],
    )
    target = make_staff_member("other@heliograph.agency")

    with pytest.raises(PermissionDenied):
        permission_services.set_override(
            user=target.user, permission_codename="seo_edit",
            effect=OverrideEffect.GRANT, actor=manager.user,
        )


def test_an_override_cannot_be_applied_to_a_client(super_admin):
    from apps.accounts.tests.factories import make_user

    client_user = make_user(email="client@abc.example")

    with pytest.raises(ValidationError, match="apply to staff"):
        permission_services.set_override(
            user=client_user, permission_codename="seo_edit",
            effect=OverrideEffect.GRANT, actor=super_admin,
        )


def test_clearing_an_override_restores_the_role(super_admin):
    profile = make_staff_member(roles=[make_role("SEO", ["seo_edit"])])
    permission_services.set_override(
        user=profile.user, permission_codename="seo_edit",
        effect=OverrideEffect.DENY, actor=super_admin,
    )
    assert not profile.user.has_perm("permissions.seo_edit")

    permission_services.clear_override(
        user=profile.user, permission_codename="seo_edit", actor=super_admin,
    )

    assert profile.user.has_perm("permissions.seo_edit")


# --- client assignments ------------------------------------------------------


def test_a_super_admin_assigns_a_staff_member_to_a_client(super_admin):
    abc = make_org("ABC Holdings")
    profile = make_staff_member()

    assignment = services.assign_to_organization(
        profile=profile, organization=abc, actor=super_admin,
        role=AssignmentRole.ACCOUNT_MANAGER,
    )

    assert assignment.is_active
    assert abc in selectors.assigned_organizations(profile.user)


def test_only_one_primary_contact_per_client(super_admin):
    abc = make_org("ABC Holdings")
    first = make_staff_member("first@heliograph.agency")
    second = make_staff_member("second@heliograph.agency")

    services.assign_to_organization(profile=first, organization=abc,
                                    actor=super_admin, is_primary=True)
    services.assign_to_organization(profile=second, organization=abc,
                                    actor=super_admin, is_primary=True)

    primaries = [a.staff_id for a in
                 selectors.staff_for_organization(abc) if a.is_primary]
    assert primaries == [second.pk]


def test_reassigning_someone_restores_an_ended_assignment(super_admin):
    abc = make_org("ABC Holdings")
    profile = make_staff_member()
    assignment = services.assign_to_organization(profile=profile, organization=abc,
                                                 actor=super_admin)
    services.end_assignment(assignment=assignment, actor=super_admin)

    services.assign_to_organization(profile=profile, organization=abc,
                                    actor=super_admin)
    assignment.refresh_from_db()

    assert assignment.status == AssignmentStatus.ACTIVE
    assert profile.assignments.count() == 1


def test_an_ended_assignment_is_kept_so_history_survives(super_admin):
    abc = make_org("ABC Holdings")
    profile = make_staff_member()
    assignment = assign_client(profile, abc)

    services.end_assignment(assignment=assignment, actor=super_admin)
    assignment.refresh_from_db()

    assert assignment.status == AssignmentStatus.ENDED
    assert assignment.ended_at is not None


def test_assigning_clients_needs_the_permission():
    specialist = make_staff_member(roles=[make_role("SEO only", ["seo_edit"])])
    other = make_staff_member("other@heliograph.agency")

    with pytest.raises(PermissionDenied):
        services.assign_to_organization(
            profile=other, organization=make_org("ABC Holdings"),
            actor=specialist.user,
        )


def test_an_invalid_assignment_role_is_refused(super_admin):
    profile = make_staff_member()

    with pytest.raises(ValidationError):
        services.assign_to_organization(
            profile=profile, organization=make_org("ABC Holdings"),
            role="overlord", actor=super_admin,
        )


# --- the staff list ----------------------------------------------------------


def test_the_staff_list_counts_clients_without_a_query_per_row(
    super_admin, django_assert_num_queries
):
    abc = make_org("ABC Holdings")
    for n in range(3):
        profile = make_staff_member(f"person{n}@heliograph.agency")
        assign_client(profile, abc)

    with django_assert_num_queries(2):  # profiles + prefetched roles
        rows = list(selectors.visible_staff(super_admin))
        assert [row.client_count for row in rows[:3]] == [1, 1, 1]


def test_the_staff_list_is_empty_without_the_view_permission():
    specialist = make_staff_member(roles=[make_role("SEO only", ["seo_edit"])])

    assert selectors.visible_staff(specialist.user).count() == 0
