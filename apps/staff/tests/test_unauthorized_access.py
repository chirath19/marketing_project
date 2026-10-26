"""Unauthorized access, across every protected surface.

Web views, object endpoints, downloads, exports and the API. Each is
driven by its real URL, as the actor who should be refused — a hidden
button proves nothing, and these are the tests that would catch it if a
guard were ever removed.

Three kinds of refusal appear here and the distinction matters:

* **302 to sign-in** — nobody is signed in yet.
* **403** — signed in, but lacking the permission or the client access.
* **404** — the object exists but belongs to someone the actor may not
  see. Used where confirming existence would itself leak something.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_org
from apps.staff.tests.factories import (
    PASSWORD,
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def abc():
    return make_org("ABC Holdings")


@pytest.fixture
def xyz():
    return make_org("XYZ Ltd")


@pytest.fixture
def seo_specialist(abc):
    """Holds seo_* and organizations_view, assigned to ABC only."""
    profile = make_staff_member(
        "seo@heliograph.agency",
        roles=[make_role("SEO Specialist",
                         ["seo_view", "seo_edit", "organizations_view",
                          "organizations_export"])],
    )
    assign_client(profile, abc)
    return profile


@pytest.fixture
def nobody():
    """Signed in, staff, but holding no permissions at all."""
    return make_staff_member("nobody@heliograph.agency")


@pytest.fixture
def super_admin():
    return make_super_admin_user()


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


# ---------------------------------------------------------------------------
# Anonymous
# ---------------------------------------------------------------------------

PROTECTED_GET_URLS = [
    ("staff:list", {}),
    ("staff:create", {}),
    ("staff:clients", {}),
    ("staff:roles", {}),
    ("staff:export_clients", {}),
]


@pytest.mark.parametrize(("url_name", "kwargs"), PROTECTED_GET_URLS)
def test_an_anonymous_visitor_is_sent_to_sign_in(client, url_name, kwargs):
    response = client.get(reverse(url_name, kwargs=kwargs))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_an_anonymous_visitor_cannot_reach_an_object_endpoint(client, abc):
    response = client.get(reverse("staff:client_detail", args=[abc.slug]))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_an_anonymous_visitor_cannot_download_an_export(client):
    response = client.get(reverse("staff:export_clients"))

    assert response.status_code == 302
    assert b"Name,Slug,Status" not in response.content


# ---------------------------------------------------------------------------
# Clients must never reach staff surfaces
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_name", "kwargs"), PROTECTED_GET_URLS)
def test_a_client_is_refused_every_staff_page(client, url_name, kwargs):
    client_user = make_user(email="client@abc.example")
    sign_in(client, client_user)

    response = client.get(reverse(url_name, kwargs=kwargs))

    assert response.status_code == 403


def test_a_client_cannot_see_a_staff_members_record(client, seo_specialist):
    sign_in(client, make_user(email="client@abc.example"))

    response = client.get(reverse("staff:detail", args=[seo_specialist.pk]))

    assert response.status_code == 403


def test_a_client_cannot_reach_a_client_object_endpoint(client, abc):
    """Even their own organization: the staff view is a different surface
    with a different rule.

    404 rather than 403, because the view resolves the client through the
    organizations domain's selector, which does not return organizations
    this actor may not see. The refusal therefore does not confirm that
    the slug exists.
    """
    client_user = make_user(email="client@abc.example")
    sign_in(client, client_user)

    response = client.get(reverse("staff:client_detail", args=[abc.slug]))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Staff without the permission
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("url_name", "kwargs"), PROTECTED_GET_URLS)
def test_staff_without_permissions_are_refused(client, nobody, url_name, kwargs):
    sign_in(client, nobody.user)

    response = client.get(reverse(url_name, kwargs=kwargs))

    assert response.status_code == 403


def test_a_specialist_cannot_open_staff_administration(client, seo_specialist):
    """They hold seo_* and organizations_view — nothing to do with staff."""
    sign_in(client, seo_specialist.user)

    assert client.get(reverse("staff:list")).status_code == 403
    assert client.get(reverse("staff:create")).status_code == 403


def test_a_specialist_cannot_create_a_staff_account(client, seo_specialist):
    from apps.staff.models import StaffProfile

    sign_in(client, seo_specialist.user)
    before = StaffProfile.objects.count()

    response = client.post(reverse("staff:create"), {
        "email": "sneaky@heliograph.agency", "full_name": "Sneaky",
        "password": "correct-horse-battery", "job_title": "", "department": "",
    })

    assert response.status_code == 403
    assert StaffProfile.objects.count() == before


def test_a_specialist_cannot_change_roles(client, seo_specialist, nobody):
    """Assigning roles is how a limited account becomes an unlimited one."""
    sign_in(client, seo_specialist.user)
    manager = make_role("Operations", ["staff_manage"])

    response = client.post(reverse("staff:set_roles", args=[nobody.pk]),
                           {"roles": [manager.pk]})

    assert response.status_code == 403
    assert nobody.roles.count() == 0


def test_a_specialist_cannot_grant_themselves_a_role(client, seo_specialist):
    sign_in(client, seo_specialist.user)
    everything = make_role("Everything", ["staff_manage", "roles_manage"])

    response = client.post(reverse("staff:set_roles", args=[seo_specialist.pk]),
                           {"roles": [everything.pk]})

    assert response.status_code == 403
    assert not seo_specialist.user.has_perm("permissions.staff_manage")


def test_a_specialist_cannot_assign_themselves_a_client(client, seo_specialist, xyz):
    """The most direct route to another client's data."""
    sign_in(client, seo_specialist.user)

    response = client.post(reverse("staff:assign_client", args=[seo_specialist.pk]),
                           {"organization": xyz.pk, "role": "specialist"})

    assert response.status_code == 403
    assert not seo_specialist.assignments.filter(organization=xyz).exists()


def test_a_specialist_cannot_change_a_roles_permissions(client, seo_specialist):
    """404, not 403: without `roles_view` the role is not visible at all,
    so the refusal does not confirm it exists. Either way the permissions
    are unchanged, which is the part that matters."""
    sign_in(client, seo_specialist.user)
    role = make_role("Analyst", ["analytics_view"])

    response = client.post(reverse("staff:role_set_permissions", args=[role.pk]),
                           {"permissions": ["staff_manage", "roles_manage"]})

    assert response.status_code == 404
    assert role.permission_codenames == {"analytics_view"}


def test_a_specialist_cannot_deactivate_a_colleague(client, seo_specialist, nobody):
    sign_in(client, seo_specialist.user)

    response = client.post(reverse("staff:set_active", args=[nobody.pk]),
                           {"active": "0"})

    assert response.status_code == 403
    nobody.user.refresh_from_db()
    assert nobody.user.status == AccountStatus.ACTIVE


# ---------------------------------------------------------------------------
# Permission held, but not for this client — the heart of the phase
# ---------------------------------------------------------------------------


def test_a_specialist_sees_only_assigned_clients_in_the_list(
    client, seo_specialist, abc, xyz
):
    sign_in(client, seo_specialist.user)

    response = client.get(reverse("staff:clients"))

    assert response.status_code == 200
    assert b"ABC Holdings" in response.content
    assert b"XYZ Ltd" not in response.content


def test_a_specialist_is_refused_an_unassigned_clients_page(
    client, seo_specialist, xyz
):
    """They hold organizations_view. They are not assigned to XYZ."""
    sign_in(client, seo_specialist.user)

    response = client.get(reverse("staff:client_detail", args=[xyz.slug]))

    assert response.status_code == 403


def test_a_specialist_can_open_an_assigned_clients_page(client, seo_specialist, abc):
    sign_in(client, seo_specialist.user)

    response = client.get(reverse("staff:client_detail", args=[abc.slug]))

    assert response.status_code == 200
    assert b"ABC Holdings" in response.content


def test_ending_an_assignment_closes_the_door_immediately(
    client, seo_specialist, abc
):
    from apps.staff.models import AssignmentStatus

    sign_in(client, seo_specialist.user)
    assert client.get(reverse("staff:client_detail", args=[abc.slug])).status_code == 200

    seo_specialist.assignments.update(status=AssignmentStatus.ENDED)

    assert client.get(reverse("staff:client_detail", args=[abc.slug])).status_code == 403


# ---------------------------------------------------------------------------
# Downloads and exports
# ---------------------------------------------------------------------------


def test_an_export_contains_only_assigned_clients(client, seo_specialist, abc, xyz):
    """An export that ignored assignments would hand over the whole client
    book in one click — around every object-level check at once."""
    sign_in(client, seo_specialist.user)

    response = client.get(reverse("staff:export_clients"))
    body = b"".join(response.streaming_content)

    assert response.status_code == 200
    assert b"ABC Holdings" in body
    assert b"XYZ Ltd" not in body


def test_an_export_is_refused_without_the_export_permission(client, abc):
    """Viewing and exporting are separate rights."""
    profile = make_staff_member(
        "viewer@heliograph.agency",
        roles=[make_role("Viewer only", ["organizations_view"])],
    )
    assign_client(profile, abc)
    sign_in(client, profile.user)

    assert client.get(reverse("staff:clients")).status_code == 200
    assert client.get(reverse("staff:export_clients")).status_code == 403


def test_a_single_client_download_is_refused_for_an_unassigned_client(
    client, seo_specialist, xyz
):
    sign_in(client, seo_specialist.user)

    response = client.get(reverse("staff:export_client", args=[xyz.slug]))

    assert response.status_code == 403
    assert b"XYZ" not in response.content


def test_a_single_client_download_works_for_an_assigned_client(
    client, seo_specialist, abc
):
    sign_in(client, seo_specialist.user)

    response = client.get(reverse("staff:export_client", args=[abc.slug]))

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert b"ABC Holdings" in response.content


def test_an_export_carries_no_internal_notes(client, super_admin, abc):
    """Staff notes are internal; an export is a file that leaves the
    building."""
    abc.notes = "SECRET-STAFF-NOTE"
    abc.save(update_fields=["notes"])
    sign_in(client, super_admin)

    body = b"".join(client.get(reverse("staff:export_clients")).streaming_content)

    assert b"SECRET-STAFF-NOTE" not in body


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


API_LIST = "/api/v1/organizations/"


def test_the_api_refuses_an_anonymous_caller(client):
    response = client.get(API_LIST)

    assert response.status_code in (401, 403)


def test_the_api_refuses_a_client_user(client):
    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(API_LIST).status_code == 403


def test_the_api_refuses_staff_without_the_permission(client, nobody):
    sign_in(client, nobody.user)

    assert client.get(API_LIST).status_code == 403


def test_the_api_lists_only_assigned_clients(client, seo_specialist, abc, xyz):
    sign_in(client, seo_specialist.user)

    response = client.get(API_LIST)
    slugs = [row["slug"] for row in response.json()["results"]]

    assert response.status_code == 200
    assert slugs == [abc.slug]


def test_the_api_hides_an_unassigned_client_from_the_detail_route(
    client, seo_specialist, xyz
):
    """Scoped out of the queryset, so it is a 404 rather than a 403 — the
    endpoint does not confirm that the client exists."""
    sign_in(client, seo_specialist.user)

    assert client.get(f"{API_LIST}{xyz.slug}/").status_code == 404


def test_the_api_refuses_a_write_without_the_edit_permission(
    client, seo_specialist, abc
):
    """Read and write are separate rights on the same endpoint."""
    sign_in(client, seo_specialist.user)

    response = client.patch(
        f"{API_LIST}{abc.slug}/", data={"display_name": "Hijacked"},
        content_type="application/json",
    )

    assert response.status_code == 403
    abc.refresh_from_db()
    assert abc.display_name != "Hijacked"


def test_the_api_allows_a_write_with_the_edit_permission(client, abc):
    profile = make_staff_member(
        "editor@heliograph.agency",
        roles=[make_role("Org editor",
                         ["organizations_view", "organizations_edit"])],
    )
    assign_client(profile, abc)
    sign_in(client, profile.user)

    response = client.patch(
        f"/api/v1/organizations/{abc.slug}/", data={"display_name": "ABC"},
        content_type="application/json",
    )

    assert response.status_code == 200
    abc.refresh_from_db()
    assert abc.display_name == "ABC"


def test_the_api_never_exposes_internal_notes(client, super_admin, abc):
    abc.notes = "SECRET-STAFF-NOTE"
    abc.save(update_fields=["notes"])
    sign_in(client, super_admin)

    response = client.get(f"{API_LIST}{abc.slug}/")

    assert "notes" not in response.json()
    assert b"SECRET-STAFF-NOTE" not in response.content


def test_the_api_refuses_a_method_it_does_not_map(client, super_admin, abc):
    """An unmapped verb is refused rather than inherited."""
    sign_in(client, super_admin)

    response = client.delete(f"{API_LIST}{abc.slug}/")

    assert response.status_code in (403, 405)


# ---------------------------------------------------------------------------
# A suspended staff account
# ---------------------------------------------------------------------------


def test_a_suspended_staff_member_loses_every_surface(client, seo_specialist, abc):
    sign_in(client, seo_specialist.user)
    assert client.get(reverse("staff:clients")).status_code == 200

    seo_specialist.user.status = AccountStatus.SUSPENDED
    seo_specialist.user.save(update_fields=["status"])

    assert client.get(reverse("staff:clients")).status_code == 302
    assert client.get(API_LIST).status_code in (401, 403)


# ---------------------------------------------------------------------------
# What the super admin may do
# ---------------------------------------------------------------------------


def test_a_super_admin_reaches_everything(client, super_admin, abc, xyz):
    sign_in(client, super_admin)

    for url in (reverse("staff:list"), reverse("staff:clients"),
                reverse("staff:roles"), reverse("staff:create"),
                reverse("staff:client_detail", args=[xyz.slug]),
                API_LIST):
        assert client.get(url).status_code == 200, url


def test_a_super_admins_export_covers_every_client(client, super_admin, abc, xyz):
    sign_in(client, super_admin)

    body = b"".join(client.get(reverse("staff:export_clients")).streaming_content)

    assert b"ABC Holdings" in body
    assert b"XYZ Ltd" in body


# ---------------------------------------------------------------------------
# The shape of a refusal
# ---------------------------------------------------------------------------


def test_an_assigned_staff_member_gets_403_not_404_for_a_client_they_cannot_touch(
    client, seo_specialist, xyz
):
    """The two refusals are chosen deliberately.

    Staff can see that other clients exist — they work at the agency — so
    being refused one is a 403. A client, or someone without the
    permission to list at all, gets a 404 instead, because confirming the
    record exists would itself be a leak.
    """
    sign_in(client, seo_specialist.user)

    assert client.get(reverse("staff:client_detail", args=[xyz.slug])).status_code == 403


def test_a_refusal_never_reveals_the_clients_name(client, seo_specialist, xyz):
    sign_in(client, seo_specialist.user)

    response = client.get(reverse("staff:client_detail", args=[xyz.slug]))

    assert b"XYZ Ltd" not in response.content
