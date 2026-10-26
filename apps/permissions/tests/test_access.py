"""Access resolution: permission AND client, and the order of overrides."""

import pytest

from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_org
from apps.permissions import access
from apps.permissions.catalogue import permission_string
from apps.permissions.models import OverrideEffect, UserPermissionOverride
from apps.staff.tests.factories import (
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db

SEO_EDIT = permission_string("seo", "edit")
SEO_VIEW = permission_string("seo", "view")


@pytest.fixture
def seo_role():
    return make_role("SEO", ["seo_view", "seo_edit"])


# ---------------------------------------------------------------------------
# The permission half
# ---------------------------------------------------------------------------


def test_a_role_grants_its_permissions(seo_role):
    profile = make_staff_member(roles=[seo_role])

    assert access.has_permission(profile.user, SEO_EDIT)


def test_nothing_is_granted_by_default():
    """The default is closed: a new staff account can sign in and do
    nothing until given a role."""
    profile = make_staff_member()

    assert access.permission_codenames_for(profile.user) == frozenset()
    assert not access.has_permission(profile.user, SEO_VIEW)


def test_a_permission_outside_the_role_is_refused(seo_role):
    profile = make_staff_member(roles=[seo_role])

    assert not access.has_permission(
        profile.user, permission_string("paid_ads", "edit"))


def test_a_super_admin_holds_everything():
    user = make_super_admin_user()

    assert access.has_permission(user, SEO_EDIT)
    assert access.has_permission(user, permission_string("staff", "manage"))
    assert access.has_permission(user, permission_string("settings", "manage"))


def test_a_client_holds_no_platform_permission():
    """A client's rights come from their organization membership, which is
    a different mechanism entirely."""
    client_user = make_user(email="client@abc.example")

    assert access.permission_codenames_for(client_user) == frozenset()
    assert not access.has_permission(client_user, SEO_VIEW)


def test_an_anonymous_actor_holds_nothing():
    from django.contrib.auth.models import AnonymousUser

    assert not access.has_permission(AnonymousUser(), SEO_VIEW)
    assert not access.has_permission(None, SEO_VIEW)


def test_a_suspended_staff_member_holds_nothing(seo_role):
    """Their role is intact; they simply cannot act while suspended."""
    from apps.accounts.models import AccountStatus

    profile = make_staff_member(roles=[seo_role], status=AccountStatus.SUSPENDED)

    assert not access.has_permission(profile.user, SEO_EDIT)


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


def test_a_grant_override_adds_a_permission_no_role_gives(seo_role):
    from django.contrib.auth.models import Permission

    from apps.permissions.catalogue import catalogue_filter

    profile = make_staff_member(roles=[seo_role])
    UserPermissionOverride.objects.create(
        user=profile.user,
        permission=Permission.objects.get(**catalogue_filter(),
                                          codename="analytics_export"),
        effect=OverrideEffect.GRANT,
    )

    assert access.has_permission(profile.user,
                                 permission_string("analytics", "export"))


def test_a_deny_override_beats_the_role(seo_role):
    """A permission withheld from one person must not be re-granted by the
    role they hold, or the override is decorative."""
    from django.contrib.auth.models import Permission

    from apps.permissions.catalogue import catalogue_filter

    profile = make_staff_member(roles=[seo_role])
    assert access.has_permission(profile.user, SEO_EDIT)

    UserPermissionOverride.objects.create(
        user=profile.user,
        permission=Permission.objects.get(**catalogue_filter(), codename="seo_edit"),
        effect=OverrideEffect.DENY,
    )
    access.clear_cache(profile.user)

    assert not access.has_permission(profile.user, SEO_EDIT)
    assert access.has_permission(profile.user, SEO_VIEW), "only the denied one goes"


def test_a_deny_override_cannot_be_undone_by_a_second_role(seo_role):
    from django.contrib.auth.models import Permission

    from apps.permissions.catalogue import catalogue_filter

    second = make_role("Also SEO", ["seo_edit"])
    profile = make_staff_member(roles=[seo_role, second])

    UserPermissionOverride.objects.create(
        user=profile.user,
        permission=Permission.objects.get(**catalogue_filter(), codename="seo_edit"),
        effect=OverrideEffect.DENY,
    )
    access.clear_cache(profile.user)

    assert not access.has_permission(profile.user, SEO_EDIT)


def test_overrides_do_not_apply_to_a_super_admin():
    """There is nothing to resolve: a super admin holds everything."""
    from django.contrib.auth.models import Permission

    from apps.permissions.catalogue import catalogue_filter

    user = make_super_admin_user()
    UserPermissionOverride.objects.create(
        user=user,
        permission=Permission.objects.get(**catalogue_filter(), codename="seo_edit"),
        effect=OverrideEffect.DENY,
    )
    access.clear_cache(user)

    assert access.has_permission(user, SEO_EDIT)


# ---------------------------------------------------------------------------
# The client-access half
# ---------------------------------------------------------------------------


def test_a_specialist_reaches_only_assigned_clients(seo_role):
    abc = make_org("ABC Holdings")
    xyz = make_org("XYZ Ltd")
    profile = make_staff_member(roles=[seo_role])
    assign_client(profile, abc)

    assert access.can_access_organization(profile.user, abc)
    assert not access.can_access_organization(profile.user, xyz)


def test_no_assignments_means_no_clients(seo_role):
    """Not an error, and not everything: a new starter sees nothing until
    they are assigned."""
    make_org("ABC Holdings")
    profile = make_staff_member(roles=[seo_role])

    assert access.accessible_organization_ids(profile.user) == frozenset()


def test_all_client_access_means_every_client(seo_role):
    make_org("ABC Holdings")
    profile = make_staff_member(roles=[seo_role], has_all_client_access=True)

    assert access.accessible_organization_ids(profile.user) is None


def test_an_ended_assignment_removes_access(seo_role):
    from apps.staff.models import AssignmentStatus

    abc = make_org("ABC Holdings")
    profile = make_staff_member(roles=[seo_role])
    assignment = assign_client(profile, abc)
    assert access.can_access_organization(profile.user, abc)

    assignment.status = AssignmentStatus.ENDED
    assignment.save(update_fields=["status"])
    access.clear_cache(profile.user)

    assert not access.can_access_organization(profile.user, abc)


# ---------------------------------------------------------------------------
# Both halves together — the rule the brief states
# ---------------------------------------------------------------------------


def test_the_right_permission_on_an_assigned_client_is_allowed(seo_role):
    abc = make_org("ABC Holdings")
    profile = make_staff_member(roles=[seo_role])
    assign_client(profile, abc)

    assert access.can(profile.user, SEO_EDIT, abc)


def test_the_right_permission_on_an_unassigned_client_is_refused(seo_role):
    """The brief's example: an SEO specialist can edit SEO campaigns, but
    only for their own clients."""
    xyz = make_org("XYZ Ltd")
    profile = make_staff_member(roles=[seo_role])
    assign_client(profile, make_org("ABC Holdings"))

    assert access.has_permission(profile.user, SEO_EDIT), "permission is held"
    assert not access.can(profile.user, SEO_EDIT, xyz), "but not on this client"


def test_the_wrong_permission_on_an_assigned_client_is_refused(seo_role):
    abc = make_org("ABC Holdings")
    profile = make_staff_member(roles=[seo_role])
    assign_client(profile, abc)

    assert not access.can(profile.user, permission_string("paid_ads", "edit"), abc)


def test_a_platform_wide_permission_is_not_scoped_to_clients():
    """The service catalogue and system settings belong to no client, so
    there is nothing to scope them to."""
    profile = make_staff_member(roles=[make_role("Editor", ["catalog_edit"])])

    assert access.can(profile.user, permission_string("catalog", "edit"))
    assert access.can(profile.user, permission_string("catalog", "edit"),
                      make_org("ABC Holdings"))


def test_an_object_belonging_to_a_client_is_scoped_even_without_a_direct_fk(seo_role):
    """A membership row reaches its organization one step away."""
    from apps.organizations.models import OrganizationMember

    abc = make_org("ABC Holdings")
    xyz = make_org("XYZ Ltd")
    outsider = make_user(email="person@xyz.example")
    membership = OrganizationMember.objects.create(organization=xyz, user=outsider)

    profile = make_staff_member(roles=[make_role("Org", ["organizations_view"])])
    assign_client(profile, abc)

    assert not access.can(profile.user,
                          permission_string("organizations", "view"), membership)


def test_resolution_is_cached_for_the_life_of_the_request(
    seo_role, django_assert_num_queries
):
    profile = make_staff_member(roles=[seo_role])
    user = profile.user

    access.permission_codenames_for(user)
    with django_assert_num_queries(0):
        access.has_permission(user, SEO_EDIT)
        access.has_permission(user, SEO_VIEW)


def test_clearing_the_cache_picks_up_a_change(seo_role):
    profile = make_staff_member(roles=[seo_role])
    assert access.has_permission(profile.user, SEO_EDIT)

    profile.roles.clear()
    access.clear_cache(profile.user)

    assert not access.has_permission(profile.user, SEO_EDIT)
