"""The catalogue, the backend, and the guards."""

import pytest
from django.contrib.auth.models import Permission

from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_org
from apps.permissions.catalogue import (
    ALL_ACTIONS,
    MODULES,
    all_codenames,
    catalogue_filter,
    is_client_scoped,
    permission_string,
    split_codename,
)
from apps.staff.tests.factories import (
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


# --- the catalogue ----------------------------------------------------------


def test_every_catalogue_permission_exists_in_the_database():
    """The migration creates them; this fails if the catalogue grows and
    `sync_permissions` has not been run."""
    declared = set(all_codenames())
    stored = set(
        Permission.objects.filter(**catalogue_filter())
        .values_list("codename", flat=True)
    )

    assert declared == stored


def test_the_catalogue_holds_no_permissions_django_created_for_our_models():
    """Django auto-creates add/change/delete/view for Role and friends
    under the same app label. Sweeping those in would resolve `add_role`
    as if it were a platform permission."""
    stored = set(
        Permission.objects.filter(**catalogue_filter())
        .values_list("codename", flat=True)
    )

    assert "add_role" not in stored
    assert "change_userpermissionoverride" not in stored


def test_sync_permissions_is_idempotent():
    from django.core.management import call_command

    before = Permission.objects.filter(**catalogue_filter()).count()
    call_command("sync_permissions", verbosity=0)

    assert Permission.objects.filter(**catalogue_filter()).count() == before


def test_every_module_declares_only_known_actions():
    for module in MODULES:
        unknown = set(module.actions) - set(ALL_ACTIONS)
        assert not unknown, f"{module.key} declares {unknown}"


def test_every_module_can_at_least_be_viewed():
    for module in MODULES:
        assert "view" in module.actions, f"{module.key} has no view action"


def test_codenames_round_trip_even_with_underscores_in_the_module():
    """`paid_ads_edit` must split as (paid_ads, edit), not (paid, ads_edit)."""
    for module in MODULES:
        for action in module.actions:
            name = f"{module.key}_{action}"
            assert split_codename(name) == (module.key, action)


def test_an_unknown_codename_does_not_resolve():
    assert split_codename("teleportation_edit") is None
    assert split_codename("seo_teleport") is None


def test_an_unknown_permission_is_treated_as_client_scoped():
    """The safer answer is the one that restricts."""
    assert is_client_scoped("permissions.something_unknown")


def test_platform_wide_modules_are_not_client_scoped():
    for key in ("catalog", "cms", "staff", "roles", "settings", "audit"):
        assert not is_client_scoped(permission_string(key, "view")), key


def test_client_delivery_modules_are_client_scoped():
    for key in ("seo", "paid_ads", "social", "campaigns", "analytics"):
        assert is_client_scoped(permission_string(key, "view")), key


# --- the backend ------------------------------------------------------------


def test_has_perm_enforces_both_halves():
    abc = make_org("ABC Holdings")
    xyz = make_org("XYZ Ltd")
    profile = make_staff_member(roles=[make_role("SEO", ["seo_edit"])])
    assign_client(profile, abc)
    user = profile.user

    assert user.has_perm("permissions.seo_edit")
    assert user.has_perm("permissions.seo_edit", abc)
    assert not user.has_perm("permissions.seo_edit", xyz)


def test_only_one_backend_is_configured(settings):
    """Django resolves has_perm as a union across backends, so a second
    one could re-grant a permission this platform denies."""
    assert settings.AUTHENTICATION_BACKENDS == [
        "apps.permissions.backends.PlatformPermissionBackend"
    ]


def test_a_django_group_cannot_re_grant_a_denied_platform_permission():
    """The concrete reason for a single backend."""
    from django.contrib.auth.models import Group

    from apps.permissions.models import OverrideEffect, UserPermissionOverride

    profile = make_staff_member(roles=[make_role("SEO", ["seo_edit"])])
    permission = Permission.objects.get(**catalogue_filter(), codename="seo_edit")

    UserPermissionOverride.objects.create(
        user=profile.user, permission=permission, effect=OverrideEffect.DENY,
    )

    group = Group.objects.create(name="Backdoor")
    group.permissions.add(permission)
    profile.user.groups.add(group)

    # Re-fetch so Django's own permission cache is cold.
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.get(pk=profile.user.pk)

    assert not user.has_perm("permissions.seo_edit")


def test_django_model_permissions_still_resolve_normally():
    """The admin needs them, so they are left to Django."""
    from django.contrib.auth.models import Group

    user = make_user(email="admin@heliograph.agency")
    from apps.accounts.models import UserType
    user.user_type = UserType.STAFF
    user.is_staff = True
    user.save(update_fields=["user_type", "is_staff"])

    permission = Permission.objects.get(
        content_type__app_label="organizations", codename="view_organization",
    )
    group = Group.objects.create(name="Admin readers")
    group.permissions.add(permission)
    user.groups.add(group)

    from django.contrib.auth import get_user_model
    reloaded = get_user_model().objects.get(pk=user.pk)

    assert reloaded.has_perm("organizations.view_organization")


def test_a_super_admin_passes_every_check():
    user = make_super_admin_user()
    abc = make_org("ABC Holdings")

    assert user.has_perm("permissions.seo_edit", abc)
    assert user.has_perm("permissions.settings_manage")
    assert user.has_perm("organizations.view_organization")


def test_template_permissions_are_filtered_by_object():
    """`{{ perms }}` with an object must not offer a control for a client
    the user may not touch."""
    from apps.permissions.backends import PlatformPermissionBackend

    abc = make_org("ABC Holdings")
    xyz = make_org("XYZ Ltd")
    profile = make_staff_member(roles=[make_role("SEO", ["seo_edit"])])
    assign_client(profile, abc)

    backend = PlatformPermissionBackend()

    assert "permissions.seo_edit" in backend.get_all_permissions(profile.user, abc)
    assert "permissions.seo_edit" not in backend.get_all_permissions(profile.user, xyz)


# --- the guards -------------------------------------------------------------


def test_ensure_can_raises_for_the_wrong_client():
    from django.core.exceptions import PermissionDenied

    from apps.permissions.guards import ensure_can

    xyz = make_org("XYZ Ltd")
    profile = make_staff_member(roles=[make_role("SEO", ["seo_edit"])])
    assign_client(profile, make_org("ABC Holdings"))

    with pytest.raises(PermissionDenied):
        ensure_can(profile.user, "seo_edit", xyz)


def test_scope_to_accessible_narrows_a_queryset():
    from apps.organizations.models import Organization
    from apps.permissions.guards import scope_to_accessible

    abc = make_org("ABC Holdings")
    make_org("XYZ Ltd")
    profile = make_staff_member(roles=[make_role("Org", ["organizations_view"])])
    assign_client(profile, abc)

    scoped = scope_to_accessible(Organization.objects.all(), profile.user, field="id")

    assert list(scoped) == [abc]


def test_scope_to_accessible_leaves_an_unrestricted_actor_alone():
    from apps.organizations.models import Organization
    from apps.permissions.guards import scope_to_accessible

    make_org("ABC Holdings")
    make_org("XYZ Ltd")
    user = make_super_admin_user()

    assert scope_to_accessible(Organization.objects.all(), user,
                               field="id").count() == 2


def test_a_mixin_without_a_permission_declared_fails_loudly():
    """Silently allowing a view that forgot to declare one would be the
    worst possible default."""
    from django.test import RequestFactory
    from django.views import View

    from apps.permissions.guards import PermissionRequiredMixin

    class Forgetful(PermissionRequiredMixin, View):
        pass

    request = RequestFactory().get("/")
    request.user = make_super_admin_user()

    with pytest.raises(ValueError, match="required_permission"):
        Forgetful().dispatch(request)


def test_platform_rights_and_django_admin_rights_are_separate():
    """`user_type` drives this platform's authorisation; `is_superuser`
    drives Django's own model permissions and the admin. The service sets
    both for a super admin, but they answer different questions and a
    `user_type` alone does not open the Django admin."""
    from apps.accounts.models import UserType

    user = make_user(email="odd@heliograph.agency", user_type=UserType.SUPER_ADMIN)
    assert not user.is_superuser

    assert user.has_perm("permissions.seo_edit"), "platform rights follow user_type"
    assert not user.has_perm("organizations.view_organization"), (
        "Django model permissions still follow is_superuser"
    )
