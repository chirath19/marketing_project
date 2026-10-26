"""The admin shell: navigation, guards and honesty about empty modules.

Every navigation section is exercised as a real route. The menu is
filtered server-side, but the tests drive URLs directly — a hidden link
has never stopped anyone typing one.
"""

import pytest
from django.urls import reverse

from apps.accounts.models import AccountStatus
from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_org
from apps.staff.navigation import NAVIGATION, visible_navigation
from apps.staff.tests.factories import (
    PASSWORD,
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db

#: Every section in the navigation, as (key, url_name, permission).
ALL_SECTIONS = [
    (item.key, item.url_name, item.permission)
    for group in NAVIGATION for item in group.items
]


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def super_admin():
    return make_super_admin_user()


@pytest.fixture
def nobody():
    """Staff, signed in, holding no permissions at all."""
    return make_staff_member("nobody@heliograph.agency")


# ---------------------------------------------------------------------------
# Every section is reachable by someone who should reach it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("key", "url_name", "permission"), ALL_SECTIONS,
                         ids=[section[0] for section in ALL_SECTIONS])
def test_a_super_admin_can_open_every_section(client, super_admin, key, url_name,
                                              permission):
    sign_in(client, super_admin)

    response = client.get(reverse(url_name))

    assert response.status_code == 200, key


@pytest.mark.parametrize(("key", "url_name", "permission"), ALL_SECTIONS,
                         ids=[section[0] for section in ALL_SECTIONS])
def test_an_anonymous_visitor_is_sent_to_sign_in(client, key, url_name, permission):
    response = client.get(reverse(url_name))

    assert response.status_code == 302, key
    assert "/accounts/login/" in response.url


@pytest.mark.parametrize(("key", "url_name", "permission"), ALL_SECTIONS,
                         ids=[section[0] for section in ALL_SECTIONS])
def test_a_client_user_is_refused_every_section(client, key, url_name, permission):
    """The staff shell is not a place a client may be, even on a page that
    would show them nothing."""
    sign_in(client, make_user(email="client@abc.example"))

    response = client.get(reverse(url_name))

    assert response.status_code == 403, key


@pytest.mark.parametrize(
    ("key", "url_name", "permission"),
    [section for section in ALL_SECTIONS if section[2]],
    ids=[section[0] for section in ALL_SECTIONS if section[2]],
)
def test_staff_without_the_permission_are_refused(client, nobody, key, url_name,
                                                  permission):
    sign_in(client, nobody.user)

    response = client.get(reverse(url_name))

    assert response.status_code in (403, 404), key


@pytest.mark.parametrize(
    ("key", "url_name", "permission"),
    [section for section in ALL_SECTIONS if section[2]],
    ids=[section[0] for section in ALL_SECTIONS if section[2]],
)
def test_the_matching_permission_opens_the_section(client, key, url_name, permission):
    """Each section is opened by its own permission and no other."""
    profile = make_staff_member(
        f"{key}@heliograph.agency", roles=[make_role(f"Just {key}", [permission])],
    )
    sign_in(client, profile.user)

    response = client.get(reverse(url_name))

    assert response.status_code == (403 if key == "settings" else 200), key


# ---------------------------------------------------------------------------
# The dashboard home
# ---------------------------------------------------------------------------


def test_any_staff_member_can_open_the_dashboard(client, nobody):
    """It carries no section permission — but it is still staff-only."""
    sign_in(client, nobody.user)

    assert client.get(reverse("staff:dashboard")).status_code == 200


def test_a_staff_member_with_no_access_is_told_so(client, nobody):
    sign_in(client, nobody.user)

    response = client.get(reverse("staff:dashboard"))

    # An explanation and a next step, not a blank panel: somebody whose
    # permissions are wrong should be told what to do about it.
    assert b"No figures to show you" in response.content
    assert b"ask an administrator" in response.content


def test_a_suspended_staff_member_cannot_open_the_dashboard(client, nobody):
    nobody.user.status = AccountStatus.SUSPENDED
    nobody.user.save(update_fields=["status"])

    response = client.get(reverse("staff:dashboard"))

    assert response.status_code == 302


# ---------------------------------------------------------------------------
# No invented data
# ---------------------------------------------------------------------------


def test_the_dashboard_shows_real_counts_only(client, super_admin):
    """Three organizations exist, so the tile says three."""
    for name in ("ABC Holdings", "XYZ Ltd", "Third Co"):
        make_org(name)
    sign_in(client, super_admin)

    response = client.get(reverse("staff:dashboard"))

    assert b">3<" in response.content.replace(b"\n", b"")


def test_the_dashboard_shows_zero_rather_than_a_placeholder_number(client, super_admin):
    sign_in(client, super_admin)

    response = client.get(reverse("staff:dashboard"))

    assert response.status_code == 200
    assert b">0<" in response.content.replace(b"\n", b"")


#: Sections whose module does not exist yet, read from the registry rather
#: than listed here — so this test stays right as modules land.
UNBUILT_SECTIONS = [
    (item.key, item.url_name, item.permission)
    for group in NAVIGATION for item in group.items if not item.built
]


@pytest.mark.parametrize(
    ("key", "url_name", "permission"), UNBUILT_SECTIONS,
    ids=[section[0] for section in UNBUILT_SECTIONS],
)
def test_an_unbuilt_section_says_so_instead_of_showing_data(
    client, super_admin, key, url_name, permission
):
    """A page of plausible-looking sample rows is how a dashboard loses
    the trust of the people who have to rely on it."""
    sign_in(client, super_admin)

    response = client.get(reverse(url_name))
    body = response.content

    assert b"Not built yet" in body, key
    assert b"has no data yet" in body, key
    assert b"<table" not in body, f"{key} renders a table with nothing real in it"


# ---------------------------------------------------------------------------
# Permission-aware navigation
# ---------------------------------------------------------------------------


def test_the_menu_shows_a_super_admin_every_section(super_admin):
    keys = {item.key for group in visible_navigation(super_admin)
            for item in group["items"]}

    assert keys == {key for key, _url, _perm in ALL_SECTIONS}


def test_the_menu_hides_sections_the_actor_cannot_open():
    profile = make_staff_member(roles=[make_role("SEO only", ["seo_view"])])

    keys = {item.key for group in visible_navigation(profile.user)
            for item in group["items"]}

    assert "seo" in keys
    assert "dashboard" in keys, "the home page needs no permission"
    assert "staff" not in keys
    assert "settings" not in keys
    assert "paid_ads" not in keys


def test_an_empty_group_is_dropped_from_the_menu():
    """A specialist should not get an empty "Administration" heading."""
    profile = make_staff_member(roles=[make_role("SEO only", ["seo_view"])])

    labels = {group["label"] for group in visible_navigation(profile.user)}

    assert "Administration" not in labels
    assert "Delivery" in labels


def test_a_client_gets_no_admin_navigation():
    assert visible_navigation(make_user(email="client@abc.example")) == []


def test_an_anonymous_visitor_gets_no_admin_navigation():
    from django.contrib.auth.models import AnonymousUser

    assert visible_navigation(AnonymousUser()) == []
    assert visible_navigation(None) == []


def test_the_rendered_menu_matches_the_permissions(client):
    """The sidebar is markup, so it is checked as markup too."""
    profile = make_staff_member(roles=[make_role("SEO only", ["seo_view"])])
    sign_in(client, profile.user)

    body = client.get(reverse("staff:dashboard")).content

    assert b'href="/staff/workspace/projects/"' in body
    assert b'href="/staff/seo/"' not in body
    tools = client.get(reverse("staff:workflow", args=["projects"])).content
    assert b'href="/staff/seo/"' in tools
    assert b'href="/staff/settings/"' not in tools
    assert b'href="/staff/roles/"' not in tools


def test_the_django_admin_link_is_only_shown_to_superusers(client, super_admin):
    """Django's admin stays available for developer work, but it is not
    the business dashboard and most staff never need it."""
    sign_in(client, super_admin)
    assert b'href="/admin/"' in client.get(reverse("staff:dashboard")).content

    client.logout()
    ordinary = make_staff_member("ordinary@heliograph.agency")
    sign_in(client, ordinary.user)

    assert b'href="/admin/"' not in client.get(reverse("staff:dashboard")).content


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_is_staff_only(client):
    sign_in(client, make_user(email="client@abc.example"))

    assert client.get(reverse("staff:search"), {"q": "abc"}).status_code == 403


def test_search_finds_an_assigned_client(client):
    abc = make_org("ABC Holdings")
    profile = make_staff_member(roles=[make_role("Org", ["organizations_view"])])
    assign_client(profile, abc)
    sign_in(client, profile.user)

    response = client.get(reverse("staff:search"), {"q": "ABC"})

    assert b"ABC Holdings" in response.content


def test_search_never_surfaces_an_unassigned_client(client):
    """Search must not be a way around the scoping every list page has."""
    abc = make_org("ABC Holdings")
    make_org("XYZ Ltd")
    profile = make_staff_member(roles=[make_role("Org", ["organizations_view"])])
    assign_client(profile, abc)
    sign_in(client, profile.user)

    response = client.get(reverse("staff:search"), {"q": "XYZ"})

    assert b"XYZ Ltd" not in response.content
    assert b"Nothing found" in response.content


def test_search_hides_staff_from_someone_without_the_permission(client):
    make_staff_member("findme@heliograph.agency")
    profile = make_staff_member(
        "searcher@heliograph.agency",
        roles=[make_role("Org", ["organizations_view"])],
    )
    sign_in(client, profile.user)

    response = client.get(reverse("staff:search"), {"q": "findme"})

    assert b"findme@heliograph.agency" not in response.content


def test_an_empty_search_asks_rather_than_listing_everything(client, super_admin):
    make_org("ABC Holdings")
    sign_in(client, super_admin)

    response = client.get(reverse("staff:search"))

    assert b"Search the dashboard" in response.content
    assert b"ABC Holdings" not in response.content


def test_search_escapes_the_query_it_echoes_back(client, super_admin):
    sign_in(client, super_admin)

    response = client.get(reverse("staff:search"), {"q": "<script>alert(1)</script>"})

    assert b"<script>alert(1)</script>" not in response.content


def test_a_built_section_is_not_marked_soon_in_the_menu(client, super_admin):
    """`built` drives both the badge and the placeholder test above, so a
    section cannot be live while still advertising itself as coming."""
    from apps.staff.navigation import item_for

    for key in ("dashboard", "clients", "staff", "roles", "cms"):
        item = item_for(key)
        assert item is not None and item.built, key
        assert not item.is_module_placeholder, key
