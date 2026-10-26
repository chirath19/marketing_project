"""Organization A cannot reach Organization B's SEO records.

Five tenant-owned models arrive with this module, and every one carries
something a competitor would like: the terms a business is targeting,
what is broken on its site, who has agreed to link to it. So the rule is
tested per model and at every layer it could be broken at.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_member, make_org
from apps.seo import selectors, services
from apps.seo.models import (
    Backlink,
    IssueStatus,
    Keyword,
    SeoAudit,
    SeoTask,
)
from apps.seo.tests.factories import (
    make_audit,
    make_backlink,
    make_issue,
    make_keyword,
    make_position,
    make_task,
)
from apps.staff.tests.factories import (
    PASSWORD,
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)

pytestmark = pytest.mark.django_db


def sign_in(client, user) -> None:  # noqa: ANN001
    assert client.login(username=user.email, password=PASSWORD)


@pytest.fixture
def two_clients():
    """Two unrelated clients, each with a full set of SEO records."""
    admin = make_super_admin_user("setup@heliograph.agency")

    org_a, org_b = make_org("Vantage Interiors"), make_org("Northwind Supply")
    user_a = make_user(email="a@vantage.example")
    user_b = make_user(email="b@northwind.example")
    make_member(org_a, user_a)
    make_member(org_b, user_b)

    a = {
        "org": org_a, "user": user_a,
        "audit": make_audit(org_a, actor=admin, title="Vantage audit"),
        "keyword": make_keyword(org_a, actor=admin, term="vantage sofas"),
        "task": make_task(org_a, actor=admin, title="Vantage homepage"),
        "link": make_backlink(org_a, actor=admin,
                              source_domain="vantage-press.example"),
    }
    b = {
        "org": org_b, "user": user_b,
        "audit": make_audit(org_b, actor=admin, title="Northwind audit"),
        "keyword": make_keyword(org_b, actor=admin, term="northwind valves"),
        "task": make_task(org_b, actor=admin, title="Northwind homepage"),
        "link": make_backlink(org_b, actor=admin,
                              source_domain="northwind-press.example"),
    }
    a["issue"] = make_issue(a["audit"], actor=admin, title="Vantage issue")
    b["issue"] = make_issue(b["audit"], actor=admin, title="Northwind issue")
    return a, b


# ---------------------------------------------------------------------------
# The querysets themselves, model by model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("model", "key"), [
    (SeoAudit, "audit"), (Keyword, "keyword"), (SeoTask, "task"),
    (Backlink, "link"),
])
def test_each_tenant_model_shows_a_client_only_their_own(two_clients, model, key):
    a, b = two_clients

    visible = set(model.objects.visible_to(a["user"]).values_list("pk", flat=True))

    assert visible == {a[key].pk}
    assert b[key].pk not in visible


def test_an_anonymous_visitor_sees_nothing(two_clients):
    from django.contrib.auth.models import AnonymousUser

    anonymous = AnonymousUser()
    for model in (SeoAudit, Keyword, SeoTask, Backlink):
        assert not model.objects.visible_to(anonymous).exists(), model.__name__


def test_a_removed_member_stops_seeing_the_records(two_clients):
    from apps.organizations.models import MemberStatus, OrganizationMember

    a, _b = two_clients
    assert Keyword.objects.visible_to(a["user"]).exists()

    OrganizationMember.objects.filter(organization=a["org"],
                                      user=a["user"]).update(
        status=MemberStatus.REMOVED)

    assert not Keyword.objects.visible_to(a["user"]).exists()


def test_findings_are_reachable_only_through_their_own_audit(two_clients):
    """`TechnicalIssue` has no organization of its own; it must still be
    impossible to reach another client's."""
    a, b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")

    theirs = selectors.get_audit(admin, b["audit"].pk)
    assert theirs is not None, "an admin sees both"

    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("SEO", ["seo_view", "organizations_view"])],
    )
    assign_client(staff, a["org"])

    assert selectors.get_audit(staff.user, b["audit"].pk) is None


# ---------------------------------------------------------------------------
# Through the staff pages
# ---------------------------------------------------------------------------


@pytest.fixture
def scoped_staff(two_clients):
    """Staff with full SEO rights, assigned to client A only."""
    a, _b = two_clients
    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("SEO", ["seo_view", "seo_create", "seo_edit",
                                 "seo_approve", "organizations_view"])],
    )
    assign_client(staff, a["org"])
    return staff


def test_scoped_staff_see_only_their_clients_records(two_clients, scoped_staff):
    a, b = two_clients

    assert {k.pk for k in selectors.visible_keywords(scoped_staff.user)} \
        == {a["keyword"].pk}
    assert {t.pk for t in selectors.visible_tasks(scoped_staff.user)} \
        == {a["task"].pk}
    assert {link.pk for link in selectors.visible_backlinks(scoped_staff.user)} \
        == {a["link"].pk}
    assert b["keyword"].pk not in {
        k.pk for k in selectors.visible_keywords(scoped_staff.user)
    }


def test_scoped_staff_get_a_404_on_another_clients_workspace(client, two_clients,
                                                             scoped_staff):
    _a, b = two_clients
    sign_in(client, scoped_staff.user)

    for name in ("staff:seo_workspace", "staff:seo_keywords",
                 "staff:seo_audits", "staff:seo_tasks", "staff:seo_backlinks"):
        response = client.get(reverse(name, args=[b["org"].slug]))
        assert response.status_code == 404, name


def test_scoped_staff_get_a_404_on_another_clients_audit(client, two_clients,
                                                         scoped_staff):
    _a, b = two_clients
    sign_in(client, scoped_staff.user)

    response = client.get(reverse("staff:seo_audit_detail",
                                  args=[b["audit"].pk]))

    assert response.status_code == 404


def test_scoped_staff_get_a_404_on_another_clients_keyword(client, two_clients,
                                                           scoped_staff):
    _a, b = two_clients
    sign_in(client, scoped_staff.user)

    response = client.get(reverse("staff:seo_keyword_detail",
                                  args=[b["keyword"].pk]))

    assert response.status_code == 404


def test_scoped_staff_cannot_write_to_another_client(two_clients, scoped_staff):
    """The service layer refuses, not just the view.

    Checked here because the views are one caller of several: the CSV
    importer goes through the same functions, and the rule has to live
    where they all meet it.
    """
    _a, b = two_clients

    with pytest.raises(PermissionDenied):
        services.add_keyword(organization=b["org"], term="sneaky",
                             actor=scoped_staff.user)

    with pytest.raises(PermissionDenied):
        services.create_audit(organization=b["org"], title="Sneaky",
                              actor=scoped_staff.user)

    with pytest.raises(PermissionDenied):
        services.set_issue_status(issue=b["issue"], status=IssueStatus.FIXED,
                                  actor=scoped_staff.user)

    with pytest.raises(PermissionDenied):
        services.deliver_audit(audit=b["audit"], actor=scoped_staff.user)


def test_scoped_staff_cannot_import_for_another_client(two_clients, scoped_staff):
    """The import path is a write like any other."""
    import io

    from apps.seo.importers import import_keyword_positions

    _a, b = two_clients

    with pytest.raises(PermissionDenied):
        import_keyword_positions(
            organization=b["org"], actor=scoped_staff.user,
            file_obj=io.StringIO("keyword,position\nsneaky,1\n"),
        )


def test_a_client_user_is_refused_the_staff_pages(client, two_clients):
    a, _b = two_clients
    sign_in(client, a["user"])

    assert client.get(reverse("staff:module_seo")).status_code == 403
    assert client.get(
        reverse("staff:seo_workspace", args=[a["org"].slug])).status_code == 403


def test_staff_without_the_permission_are_refused(client, two_clients):
    nobody = make_staff_member("nobody@heliograph.agency")
    sign_in(client, nobody.user)

    assert client.get(reverse("staff:module_seo")).status_code == 403


def test_search_never_crosses_the_boundary(two_clients, scoped_staff):
    """A search box is a classic way round a scoped list."""
    _a, b = two_clients

    found = selectors.visible_keywords(scoped_staff.user, search="northwind")

    assert b["keyword"].pk not in {k.pk for k in found}
    assert list(found) == []


def test_the_client_list_shows_only_assigned_clients(client, two_clients,
                                                     scoped_staff):
    a, b = two_clients
    sign_in(client, scoped_staff.user)

    body = client.get(reverse("staff:module_seo")).content

    assert a["org"].label.encode() in body
    assert b["org"].label.encode() not in body


# ---------------------------------------------------------------------------
# Through the client's own portal
# ---------------------------------------------------------------------------


def _give_seo_service(organization):  # noqa: ANN001
    """An active Search service, so the portal area opens at all."""
    from apps.staff.tests.factories import make_super_admin_user as admin_user
    from apps.subscriptions.models import SubscriptionStatus
    from apps.subscriptions.tests.factories import make_service, make_subscription

    return make_subscription(
        organization, actor=admin_user("subs@heliograph.agency"),
        service=make_service("SEO retainer", category_slug="search",
                             workspace_module="seo"),
        status=SubscriptionStatus.ACTIVE,
    )


def test_a_clients_seo_area_never_names_another_client(client, two_clients):
    a, b = two_clients
    _give_seo_service(a["org"])
    make_position(a["keyword"])
    sign_in(client, a["user"])

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert a["keyword"].term.encode() in body
    assert b["keyword"].term.encode() not in body
    assert b["org"].label.encode() not in body


def test_the_client_workspace_selector_is_scoped(two_clients):
    a, b = two_clients

    workspace = selectors.client_workspace(a["user"])

    assert workspace["organization"] == a["org"]
    terms = {keyword.term for keyword in workspace["keywords"]}
    assert b["keyword"].term not in terms


# ---------------------------------------------------------------------------
# What is withheld from the client
# ---------------------------------------------------------------------------


def test_an_undelivered_audit_is_not_shown_to_the_client(client, two_clients):
    """Work in progress read as a finished finding causes exactly the
    conversation it was meant to prevent."""
    a, _b = two_clients
    _give_seo_service(a["org"])
    make_position(a["keyword"])
    services.update_audit(audit=a["audit"],
                          actor=make_super_admin_user("boss@heliograph.agency"),
                          summary="Half-written thoughts, not final.")
    sign_in(client, a["user"])

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"Half-written thoughts" not in body


def test_a_delivered_audit_is_shown(client, two_clients):
    a, _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")
    _give_seo_service(a["org"])
    make_position(a["keyword"])
    services.update_audit(audit=a["audit"], actor=admin,
                          summary="Three things are slowing the site down.")
    services.deliver_audit(audit=a["audit"], actor=admin)
    sign_in(client, a["user"])

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"Three things are slowing the site down" in body


def test_audit_internal_notes_never_reach_the_client(client, two_clients):
    a, _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")
    _give_seo_service(a["org"])
    make_position(a["keyword"])
    services.update_audit(audit=a["audit"], actor=admin,
                          summary="A readable summary.",
                          internal_notes="Their developer is the problem.")
    services.deliver_audit(audit=a["audit"], actor=admin)
    sign_in(client, a["user"])

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"Their developer" not in body


def test_a_task_with_no_client_summary_stays_internal(client, two_clients):
    a, _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")
    _give_seo_service(a["org"])
    make_position(a["keyword"])
    make_task(a["org"], actor=admin, title="Internal tidy-up of the sitemap")
    sign_in(client, a["user"])

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"Internal tidy-up" not in body


def test_a_task_with_a_summary_is_shown(client, two_clients):
    a, _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")
    _give_seo_service(a["org"])
    make_position(a["keyword"])
    make_task(a["org"], actor=admin, title="Rewrite the range pages",
              client_summary="We rewrote your three main range pages.")
    sign_in(client, a["user"])

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"rewrote your three main range pages" in body


def test_backlink_notes_never_reach_the_client(client, two_clients):
    a, _b = two_clients
    admin = make_super_admin_user("boss@heliograph.agency")
    _give_seo_service(a["org"])
    make_position(a["keyword"])
    make_backlink(a["org"], actor=admin, source_domain="useful-site.example",
                  status="live", notes="Cost us a favour, do not repeat.")
    sign_in(client, a["user"])

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"Cost us a favour" not in body


def test_the_seo_area_is_refused_without_an_active_search_service(client,
                                                                  two_clients):
    """The portal's entitlement rule still applies — SEO records do not
    open an area the client has not bought."""
    a, _b = two_clients
    make_position(a["keyword"])
    sign_in(client, a["user"])

    response = client.get(reverse("organizations:portal_module", args=["seo"]))

    assert response.status_code == 403
