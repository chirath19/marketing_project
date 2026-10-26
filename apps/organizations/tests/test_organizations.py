"""Organizations, memberships and the services that change them."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import PASSWORD, make_staff, make_super_admin, make_user
from apps.organizations import selectors, services
from apps.organizations.models import (
    MemberRole,
    MemberStatus,
    Organization,
    OrganizationMember,
    OrganizationStatus,
)
from apps.organizations.tests.factories import make_member, make_org, make_tenant

pytestmark = pytest.mark.django_db


# --- the shape the brief describes -----------------------------------------


def test_one_company_holds_several_people_with_different_roles():
    """ABC Holdings: an owner, a marketing manager and a finance user —
    one company, three accounts, not three companies."""
    abc, owner = make_tenant("ABC Holdings", owner_email="owner@abc.example")
    marketing = make_user(email="marketing@abc.example")
    finance = make_user(email="finance@abc.example")

    services.add_member(organization=abc, user=marketing,
                        role=MemberRole.ADMIN, actor=owner)
    services.add_member(organization=abc, user=finance,
                        role=MemberRole.VIEWER, actor=owner)

    roles = dict(
        OrganizationMember.objects.filter(organization=abc)
        .values_list("user__email", "role")
    )

    assert roles == {
        "owner@abc.example": MemberRole.OWNER,
        "marketing@abc.example": MemberRole.ADMIN,
        "finance@abc.example": MemberRole.VIEWER,
    }
    assert Organization.objects.count() == 1


# --- slugs ------------------------------------------------------------------


def test_a_slug_is_generated_from_the_name():
    organization = services.create_organization(name="ABC Holdings")

    assert organization.slug == "abc-holdings"


def test_two_companies_with_the_same_name_both_get_a_slug():
    """Genuinely happens, and a registration must not fail because of it."""
    first = services.create_organization(name="Vantage")
    second = services.create_organization(name="Vantage")

    assert first.slug == "vantage"
    assert second.slug == "vantage-2"
    assert first.slug != second.slug


def test_a_name_with_no_usable_characters_still_gets_a_slug():
    organization = services.create_organization(name="!!!")

    assert organization.slug


def test_an_organization_needs_a_name():
    with pytest.raises(ValidationError):
        services.create_organization(name="   ")


# --- display ----------------------------------------------------------------


def test_the_display_name_wins_over_the_legal_name():
    organization = make_org("ABC Holdings Pty Ltd", display_name="ABC")

    assert organization.label == "ABC"


def test_the_legal_name_is_used_when_there_is_no_trading_name():
    assert make_org("ABC Holdings").label == "ABC Holdings"


def test_the_address_skips_the_parts_that_are_blank():
    organization = make_org(
        "ABC", address_line1="1 Main St", city="Colombo",
        postal_code="00100", country="Sri Lanka",
    )

    assert organization.address_lines == ["1 Main St", "Colombo 00100", "Sri Lanka"]


# --- status -----------------------------------------------------------------


def test_a_new_organization_starts_pending():
    assert services.create_organization(name="ABC").status == OrganizationStatus.PENDING


def test_staff_can_activate_and_suspend_a_client():
    organization = services.create_organization(name="ABC")
    staff = make_staff()

    services.activate_organization(organization=organization, actor=staff)
    assert organization.status == OrganizationStatus.ACTIVE

    services.suspend_organization(organization=organization, actor=staff)
    assert organization.status == OrganizationStatus.SUSPENDED


def test_a_client_cannot_change_their_own_organizations_status():
    """It is a commercial control; a client lifting their own suspension
    would make it meaningless."""
    organization, owner = make_tenant("ABC Holdings")

    with pytest.raises(PermissionDenied):
        services.suspend_organization(organization=organization, actor=owner)


def test_an_undefined_status_transition_is_refused():
    organization = services.create_organization(name="ABC")
    staff = make_staff()

    with pytest.raises(ValidationError):
        services.change_organization_status(
            organization=organization,
            new_status=OrganizationStatus.SUSPENDED, actor=staff,
        )


def test_an_archived_organization_is_kept_not_deleted():
    organization, _owner = make_tenant("ABC Holdings")
    services.archive_organization(organization=organization, actor=make_staff())

    assert Organization.objects.filter(pk=organization.pk).exists()
    assert organization.status == OrganizationStatus.ARCHIVED


# --- editing ----------------------------------------------------------------


def test_an_owner_can_edit_the_company_details():
    organization, owner = make_tenant("ABC Holdings")

    services.update_organization(
        organization=organization, actor=owner,
        display_name="ABC", website="https://abc.example", city="Colombo",
    )
    organization.refresh_from_db()

    assert organization.display_name == "ABC"
    assert organization.city == "Colombo"


def test_a_plain_member_cannot_edit_the_company_details():
    organization, _owner = make_tenant("ABC Holdings")
    member = make_user(email="member@abc.example")
    make_member(organization, member, role=MemberRole.MEMBER)

    with pytest.raises(PermissionDenied):
        services.update_organization(organization=organization, actor=member,
                                     display_name="Hijacked")


def test_a_viewer_cannot_edit_the_company_details():
    organization, _owner = make_tenant("ABC Holdings")
    viewer = make_user(email="viewer@abc.example")
    make_member(organization, viewer, role=MemberRole.VIEWER)

    with pytest.raises(PermissionDenied):
        services.update_organization(organization=organization, actor=viewer,
                                     display_name="Hijacked")


def test_internal_notes_cannot_be_written_through_the_profile_service():
    """They are staff-only; the field must not ride in on a crafted POST."""
    organization, owner = make_tenant("ABC Holdings")

    with pytest.raises(ValidationError):
        services.update_organization(organization=organization, actor=owner,
                                     notes="trying to write staff notes")


def test_a_client_cannot_write_internal_notes():
    organization, owner = make_tenant("ABC Holdings")

    with pytest.raises(PermissionDenied):
        services.update_internal_notes(organization=organization, actor=owner,
                                       notes="nope")


def test_staff_can_write_internal_notes():
    organization, _owner = make_tenant("ABC Holdings")
    staff = make_staff()

    services.update_internal_notes(organization=organization, actor=staff,
                                   notes="Pays on time.")
    organization.refresh_from_db()

    assert organization.notes == "Pays on time."


def test_internal_notes_are_not_shown_to_the_client(client):
    organization, owner = make_tenant("ABC Holdings")
    services.update_internal_notes(organization=organization, actor=make_staff(),
                                   notes="SECRET-STAFF-NOTE")
    client.login(username=owner.email, password=PASSWORD)

    for url in ("organizations:overview", "organizations:settings"):
        response = client.get(reverse(url))
        assert b"SECRET-STAFF-NOTE" not in response.content, url


# --- members ----------------------------------------------------------------


def test_one_person_holds_one_place_in_a_company():
    organization, owner = make_tenant("ABC Holdings")
    member = make_user(email="member@abc.example")
    services.add_member(organization=organization, user=member, actor=owner)

    with pytest.raises(ValidationError, match="already a member"):
        services.add_member(organization=organization, user=member, actor=owner)


def test_re_adding_someone_who_left_reactivates_their_place():
    organization, owner = make_tenant("ABC Holdings")
    member = make_user(email="member@abc.example")
    membership = services.add_member(organization=organization, user=member,
                                     actor=owner)
    services.remove_member(membership=membership, actor=owner)

    services.add_member(organization=organization, user=member,
                        role=MemberRole.ADMIN, actor=owner)
    membership.refresh_from_db()

    assert membership.status == MemberStatus.ACTIVE
    assert membership.role == MemberRole.ADMIN
    assert OrganizationMember.objects.filter(
        organization=organization, user=member).count() == 1


def test_a_removed_member_keeps_their_row_so_history_survives():
    organization, owner = make_tenant("ABC Holdings")
    member = make_user(email="member@abc.example")
    membership = services.add_member(organization=organization, user=member,
                                     actor=owner)

    services.remove_member(membership=membership, actor=owner)

    assert OrganizationMember.objects.filter(pk=membership.pk).exists()
    membership.refresh_from_db()
    assert membership.status == MemberStatus.REMOVED


def test_a_plain_member_cannot_add_people():
    organization, _owner = make_tenant("ABC Holdings")
    member = make_user(email="member@abc.example")
    make_member(organization, member, role=MemberRole.MEMBER)
    outsider = make_user(email="outsider@example.com")

    with pytest.raises(PermissionDenied):
        services.add_member(organization=organization, user=outsider, actor=member)


def test_an_admin_can_add_people():
    organization, _owner = make_tenant("ABC Holdings")
    admin = make_user(email="admin@abc.example")
    make_member(organization, admin, role=MemberRole.ADMIN)
    newcomer = make_user(email="new@abc.example")

    services.add_member(organization=organization, user=newcomer, actor=admin)

    assert OrganizationMember.objects.filter(
        organization=organization, user=newcomer).exists()


def test_nobody_promotes_themselves():
    """An admin must not be able to make themselves an owner."""
    organization, _owner = make_tenant("ABC Holdings")
    admin = make_user(email="admin@abc.example")
    membership = make_member(organization, admin, role=MemberRole.ADMIN)

    with pytest.raises(PermissionDenied):
        services.change_member_role(membership=membership,
                                    new_role=MemberRole.OWNER, actor=admin)


def test_the_last_owner_cannot_be_demoted():
    """An organization with nobody in charge cannot add members, change
    its details or hand over control — it would need staff to recover."""
    organization, owner = make_tenant("ABC Holdings")
    membership = OrganizationMember.objects.get(user=owner)
    staff = make_staff()

    with pytest.raises(ValidationError, match="only owner"):
        services.change_member_role(membership=membership,
                                    new_role=MemberRole.MEMBER, actor=staff)


def test_the_last_owner_cannot_be_removed():
    organization, owner = make_tenant("ABC Holdings")
    membership = OrganizationMember.objects.get(user=owner)

    with pytest.raises(ValidationError, match="only owner"):
        services.remove_member(membership=membership, actor=owner)


def test_an_owner_can_step_down_once_someone_else_owns_it():
    organization, owner = make_tenant("ABC Holdings")
    successor = make_user(email="successor@abc.example")
    services.add_member(organization=organization, user=successor,
                        role=MemberRole.OWNER, actor=owner)

    membership = OrganizationMember.objects.get(user=owner)
    services.change_member_role(membership=membership,
                                new_role=MemberRole.ADMIN, actor=make_staff())

    membership.refresh_from_db()
    assert membership.role == MemberRole.ADMIN
    assert selectors.active_owner_count(organization) == 1


def test_an_invalid_role_is_refused():
    organization, owner = make_tenant("ABC Holdings")
    outsider = make_user(email="outsider@example.com")

    with pytest.raises(ValidationError):
        services.add_member(organization=organization, user=outsider,
                            role="emperor", actor=owner)


# --- onboarding --------------------------------------------------------------


def test_registration_creates_the_organization_and_makes_the_client_its_owner(client):
    from apps.accounts.tests.factories import REGISTRATION_POST

    client.post(reverse("accounts:register"), REGISTRATION_POST)

    organization = Organization.objects.get(name="Vantage Interiors")
    membership = OrganizationMember.objects.get(organization=organization)

    assert membership.user.email == "priya@vantage.example"
    assert membership.role == MemberRole.OWNER
    # The account is pending approval, so the company is too.
    assert organization.status == OrganizationStatus.PENDING


def test_a_client_without_an_organization_is_sent_to_onboarding(client):
    user = make_user(email="orphan@example.com")
    client.login(username=user.email, password=PASSWORD)

    response = client.get(reverse("organizations:overview"))

    assert response.status_code == 302
    assert response.url == reverse("organizations:setup")


def test_onboarding_creates_the_organization_with_the_client_as_owner(client):
    user = make_user(email="orphan@example.com")
    client.login(username=user.email, password=PASSWORD)

    response = client.post(reverse("organizations:setup"), {
        "name": "Late Starter Ltd", "website": "", "phone": "", "country": "",
    })

    assert response.status_code == 302
    membership = OrganizationMember.objects.get(user=user)
    assert membership.organization.name == "Late Starter Ltd"
    assert membership.role == MemberRole.OWNER


def test_onboarding_cannot_be_used_to_spawn_extra_organizations(client):
    _organization, owner = make_tenant("ABC Holdings")
    client.login(username=owner.email, password=PASSWORD)

    response = client.post(reverse("organizations:setup"), {"name": "Sneaky Ltd"})

    assert response.status_code == 302
    assert not Organization.objects.filter(name="Sneaky Ltd").exists()


def test_staff_do_not_get_an_onboarding_page(client):
    staff = make_staff()
    client.login(username=staff.email, password=PASSWORD)

    assert client.get(reverse("organizations:setup")).status_code == 404


def test_a_registration_without_a_company_name_still_creates_the_account():
    """A missing company name is not a reason to lose a registration; the
    onboarding step asks for it on first sign-in."""
    from apps.accounts import services as account_services

    result = account_services.register_client(
        email="nocompany@example.com", password=PASSWORD, company_name="",
    )

    assert result.user.pk
    assert result.organization is None
    assert selectors.user_needs_onboarding(result.user)


# --- selectors ---------------------------------------------------------------


def test_the_primary_organization_prefers_one_the_user_owns():
    owned, user = make_tenant("Owned Co", owner_email="person@example.com")
    joined = make_org("Joined Co")
    make_member(joined, user, role=MemberRole.VIEWER)

    assert selectors.primary_organization_for(user) == owned


def test_staff_need_no_onboarding():
    assert not selectors.user_needs_onboarding(make_staff())
    assert not selectors.user_needs_onboarding(make_super_admin())


def test_the_staff_client_list_counts_members_without_a_query_per_row(
    django_assert_num_queries,
):
    staff = make_staff()
    for name in ("ABC Holdings", "XYZ Ltd", "Third Co"):
        organization, _owner = make_tenant(name)

    with django_assert_num_queries(1):
        rows = list(selectors.staff_organization_list(staff))
        assert [row.member_count for row in rows] == [1, 1, 1]


def test_the_staff_client_list_can_be_searched_and_filtered():
    staff = make_staff()
    make_tenant("ABC Holdings")
    make_tenant("XYZ Ltd", org_status=OrganizationStatus.SUSPENDED)

    assert selectors.staff_organization_list(staff, search="abc").count() == 1
    assert selectors.staff_organization_list(
        staff, status=OrganizationStatus.SUSPENDED).count() == 1


def test_a_pending_account_still_belongs_to_its_organization():
    """Approval of the account and membership of the company are separate
    facts; the second must not be lost while the first is pending."""
    organization, owner = make_tenant(
        "ABC Holdings", account_status=AccountStatus.PENDING,
        org_status=OrganizationStatus.PENDING,
    )

    assert selectors.membership_for(owner, organization) is not None
