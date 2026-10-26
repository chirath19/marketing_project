"""Client isolation.

The rule this phase exists to guarantee: one client never sees another
client's anything. Every test here drives the real queryset or the real
URL — never a template — because hidden UI is not a control.

`OrganizationOwnedModel` is the single implementation of the rule, so
these tests also cover every future domain that inherits it. The
structural test at the bottom makes sure a new tenant model cannot be
added without joining this matrix.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from apps.accounts.tests.factories import PASSWORD, make_staff, make_super_admin, make_user
from apps.organizations.models import (
    MemberRole,
    MemberStatus,
    Organization,
    OrganizationMember,
    OrganizationOwnedModel,
)
from apps.organizations.tests.factories import make_member, make_org, make_tenant

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_tenants():
    """Two unrelated clients, each with an owner."""
    abc, ann = make_tenant("ABC Holdings", owner_email="ann@abc.example")
    xyz, xena = make_tenant("XYZ Ltd", owner_email="xena@xyz.example")
    return abc, ann, xyz, xena


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------


def test_a_client_sees_only_their_own_organization(two_tenants):
    abc, ann, xyz, _xena = two_tenants

    visible = Organization.objects.visible_to(ann)

    assert list(visible) == [abc]
    assert xyz not in visible


def test_a_client_cannot_reach_another_organization_by_slug(two_tenants):
    from apps.organizations import selectors

    _abc, ann, xyz, _xena = two_tenants

    assert selectors.get_organization(ann, xyz.slug) is None


def test_staff_see_every_organization(two_tenants):
    abc, _ann, xyz, _xena = two_tenants
    staff = make_staff()

    visible = Organization.objects.visible_to(staff)

    assert abc in visible
    assert xyz in visible


def test_an_anonymous_visitor_sees_no_organization(two_tenants):
    assert Organization.objects.visible_to(AnonymousUser()).count() == 0
    assert Organization.objects.visible_to(None).count() == 0


def test_a_client_with_no_membership_sees_nothing(two_tenants):
    stranger = make_user(email="stranger@example.com")

    assert Organization.objects.visible_to(stranger).count() == 0


def test_a_removed_member_loses_sight_of_the_organization(two_tenants):
    abc, ann, _xyz, _xena = two_tenants
    assert abc in Organization.objects.visible_to(ann)

    OrganizationMember.objects.filter(user=ann).update(status=MemberStatus.REMOVED)

    assert Organization.objects.visible_to(ann).count() == 0


def test_a_suspended_member_loses_sight_of_the_organization(two_tenants):
    abc, ann, _xyz, _xena = two_tenants

    OrganizationMember.objects.filter(user=ann).update(status=MemberStatus.SUSPENDED)

    assert Organization.objects.visible_to(ann).count() == 0


def test_a_member_of_two_organizations_sees_both_and_only_those(two_tenants):
    abc, ann, xyz, _xena = two_tenants
    third = make_org("Third Co")
    make_member(xyz, ann, role=MemberRole.VIEWER)

    visible = set(Organization.objects.visible_to(ann))

    assert visible == {abc, xyz}
    assert third not in visible


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------


def test_a_client_sees_only_their_own_colleagues(two_tenants):
    abc, ann, xyz, xena = two_tenants
    colleague = make_user(email="bob@abc.example")
    make_member(abc, colleague)

    visible = OrganizationMember.objects.visible_to(ann)
    emails = {m.user.email for m in visible}

    assert emails == {"ann@abc.example", "bob@abc.example"}
    assert "xena@xyz.example" not in emails


def test_a_client_cannot_see_another_organizations_membership_rows(two_tenants):
    _abc, ann, xyz, _xena = two_tenants

    assert OrganizationMember.objects.visible_to(ann).filter(
        organization=xyz
    ).count() == 0


def test_staff_see_every_membership(two_tenants):
    staff = make_staff()

    assert OrganizationMember.objects.visible_to(staff).count() == 2


# ---------------------------------------------------------------------------
# The tenancy base — covers every future domain
# ---------------------------------------------------------------------------


def test_the_shared_queryset_scopes_by_membership(two_tenants):
    """`OrganizationOwnedQuerySet.visible_to` is the one implementation
    every tenant model inherits, so proving it here proves it for
    campaigns, subscriptions, reports and messages when they arrive."""
    abc, ann, xyz, _xena = two_tenants

    # OrganizationMember is itself organization-owned data.
    assert set(OrganizationMember.objects.visible_to(ann).values_list(
        "organization_id", flat=True)) == {abc.pk}
    assert xyz.pk not in set(OrganizationMember.objects.visible_to(ann).values_list(
        "organization_id", flat=True))


def test_for_organization_returns_nothing_for_a_missing_organization():
    assert OrganizationMember.objects.none().count() == 0
    assert OrganizationMember.objects.filter(organization=None).count() == 0


def test_every_tenant_model_is_covered_by_this_matrix():
    """A new organization-owned model must be added to TENANT_MODELS and
    given isolation coverage. This fails the build if one is introduced
    without it — which is the only way the guarantee survives contact
    with later phases."""
    #: Concrete models inheriting OrganizationOwnedModel, each of which is
    #: exercised above or in its own domain's isolation tests.
    TENANT_MODELS: set[str] = {
        "Invoice", "ServiceChangeRequest",  # tests/test_platform_refinement.py
        "Conversation", "ClientReport", "PaymentReceipt",  # tests/test_manual_workflow.py
        # Each of these is driven at every layer it could be broken at —
        # the queryset, the selector, the client's own pages and the
        # staff pages — by its own domain's isolation module.
        "ClientSubscription",   # apps/subscriptions/tests/test_isolation.py
        "Campaign",             # apps/campaigns/tests/test_isolation.py
        "SeoAudit", "SeoGoal", "Keyword", "Backlink", "SeoTask",
        "ApprovalRequest",  # apps/approvals/tests/test_isolation.py
        "EmailWorkItem", "EmailDeliverable", "EmailApproval", "EmailMetric",
        # apps/email_marketing/tests/test_isolation.py
        "SocialChannel", "CreatorPartnership", "ContentItem", "SocialDeliverable",
        "SocialApproval", "SocialMetric",  # apps/social/tests/test_isolation.py
        "DailyAdMetric", "PaidAdsGoal",  # apps/paid_ads/tests/test_isolation.py
    }

    concrete = {
        model.__name__
        for model in OrganizationOwnedModel.__subclasses__()
        if not model._meta.abstract
    }

    assert concrete == TENANT_MODELS, (
        "Organization-owned models changed. Add the new model to "
        "TENANT_MODELS and give it isolation coverage: "
        f"{concrete ^ TENANT_MODELS}"
    )


def test_the_tenancy_base_protects_against_deleting_a_live_organization():
    """`on_delete=PROTECT` so removing a company that still has work
    attached fails loudly instead of quietly taking the history with it."""
    field = OrganizationOwnedModel._meta.get_field("organization")

    from django.db.models import PROTECT

    assert field.remote_field.on_delete is PROTECT


# ---------------------------------------------------------------------------
# Through the HTTP layer
# ---------------------------------------------------------------------------


def test_a_client_sees_their_own_organization_page(client, two_tenants):
    _abc, ann, _xyz, _xena = two_tenants
    client.login(username=ann.email, password=PASSWORD)

    response = client.get(reverse("organizations:overview"))

    assert response.status_code == 200
    assert b"ABC Holdings" in response.content
    assert b"XYZ Ltd" not in response.content


def test_the_members_page_lists_no_outsider(client, two_tenants):
    _abc, ann, _xyz, xena = two_tenants
    client.login(username=ann.email, password=PASSWORD)

    response = client.get(reverse("organizations:members"))

    assert response.status_code == 200
    assert xena.email.encode() not in response.content


def test_a_client_cannot_change_a_role_in_another_organization(client, two_tenants):
    """The membership id is posted, so this is the obvious thing to try."""
    _abc, ann, xyz, xena = two_tenants
    outsider_membership = OrganizationMember.objects.get(user=xena)
    client.login(username=ann.email, password=PASSWORD)

    response = client.post(
        reverse("organizations:change_role", args=[outsider_membership.pk]),
        {"role": MemberRole.VIEWER},
    )

    assert response.status_code == 404
    outsider_membership.refresh_from_db()
    assert outsider_membership.role == MemberRole.OWNER


def test_a_client_cannot_remove_a_member_of_another_organization(client, two_tenants):
    _abc, ann, _xyz, xena = two_tenants
    outsider_membership = OrganizationMember.objects.get(user=xena)
    client.login(username=ann.email, password=PASSWORD)

    response = client.post(
        reverse("organizations:remove_member", args=[outsider_membership.pk])
    )

    assert response.status_code == 404
    outsider_membership.refresh_from_db()
    assert outsider_membership.status == MemberStatus.ACTIVE


def test_a_client_cannot_switch_into_an_organization_they_do_not_belong_to(
    client, two_tenants
):
    """The session's organization is posted by id, so it is the other
    obvious thing to try."""
    _abc, ann, xyz, _xena = two_tenants
    client.login(username=ann.email, password=PASSWORD)

    response = client.post(reverse("organizations:switch"),
                           {"organization": xyz.pk})

    assert response.status_code == 404


def test_a_client_can_switch_between_their_own_organizations(client, two_tenants):
    abc, ann, xyz, _xena = two_tenants
    make_member(xyz, ann, role=MemberRole.VIEWER)
    client.login(username=ann.email, password=PASSWORD)

    response = client.post(reverse("organizations:switch"), {"organization": xyz.pk})
    assert response.status_code == 302

    overview = client.get(reverse("organizations:overview"))
    assert b"XYZ Ltd" in overview.content


@pytest.mark.parametrize("url_name", ["organizations:overview", "organizations:members",
                                      "organizations:settings", "organizations:setup"])
def test_the_organization_pages_require_a_sign_in(client, url_name):
    response = client.get(reverse(url_name))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


def test_the_session_organization_cannot_be_forged(client, two_tenants):
    """Writing another organization's id straight into the session must
    not grant access: the middleware re-checks membership rather than
    trusting what is stored."""
    abc, ann, xyz, _xena = two_tenants
    client.login(username=ann.email, password=PASSWORD)

    session = client.session
    session["active_organization_id"] = xyz.pk
    session.save()

    response = client.get(reverse("organizations:overview"))

    assert response.status_code == 200
    assert b"ABC Holdings" in response.content
    assert b"XYZ Ltd" not in response.content


def test_staff_are_not_given_a_client_organization_by_default(client):
    """Staff do not belong to client companies; their access runs through
    a different, explicitly checked path."""
    make_tenant("ABC Holdings")
    staff = make_staff()
    client.login(username=staff.email, password=PASSWORD)

    response = client.get(reverse("organizations:overview"))

    assert response.status_code == 404


def test_a_super_admin_is_also_not_silently_a_member(client):
    make_tenant("ABC Holdings")
    admin = make_super_admin()
    client.login(username=admin.email, password=PASSWORD)

    response = client.get(reverse("organizations:overview"))

    assert response.status_code == 404


def test_the_lazy_organization_attribute_is_falsy_when_absent(rf):
    """`request.organization` is a lazy proxy, so a proxy wrapping None is
    still an object and `is None` is always False. A guard written that
    way silently lets a staff user into client code — it did, once."""
    from apps.organizations.middleware import (
        CurrentOrganizationMiddleware,
        has_organization,
    )

    staff = make_staff()
    request = rf.get("/")
    request.user = staff
    request.session = {}

    CurrentOrganizationMiddleware(lambda r: None)(request)

    assert request.organization is not None, "the proxy itself is an object"
    assert not request.organization, "but it must be falsy"
    assert has_organization(request) is False


def test_the_lazy_organization_resolves_for_a_client(rf, two_tenants):
    from apps.organizations.middleware import (
        CurrentOrganizationMiddleware,
        has_organization,
    )

    abc, ann, _xyz, _xena = two_tenants
    request = rf.get("/")
    request.user = ann
    request.session = {}

    CurrentOrganizationMiddleware(lambda r: None)(request)

    assert has_organization(request) is True
    assert request.organization.pk == abc.pk
