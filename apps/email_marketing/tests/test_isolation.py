import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.campaigns.tests.factories import make_campaign
from apps.email_marketing import selectors, services
from apps.email_marketing.models import METRICS, EmailDeliverable, EmailMetric
from apps.organizations.models import OrganizationMember
from apps.organizations.tests.factories import make_member, make_tenant
from apps.staff.tests.factories import make_role, make_staff_member
from apps.subscriptions.tests.factories import make_service, make_subscription

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "selector", ["campaigns_for", "work_for", "deliverables_for", "reviews_for", "metrics_for"]
)
def test_all_reads_enforce_tenant_membership_and_assignment(workspace, executed, selector):
    w = workspace
    services.record_metrics(
        actor=w["staff"],
        organization=w["org"],
        work=executed,
        date=timezone.localdate(),
        source="Daily report",
        **dict.fromkeys(METRICS, 1),
    )
    select = getattr(selectors, selector)
    assert select(w["staff"], w["org"]).exists()
    assert select(w["user"], w["org"]).exists()
    other, outsider = make_tenant("Other email client")
    unassigned = make_staff_member(
        email="unassigned-email@example.com",
        roles=[make_role("Email unassigned", ["email_marketing_view", "email_marketing_edit"])],
    )
    for actor in [outsider, unassigned.user, None, AnonymousUser()]:
        assert not select(actor, w["org"]).exists()
    assert not select(w["user"], other).exists()


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_authorized_client_roles_can_approve(workspace, review, role):
    w = workspace
    OrganizationMember.objects.filter(user=w["user"]).update(role=role)
    approval = services.decide_review(
        actor=w["user"], organization=w["org"], approval=review, decision="approved"
    )
    assert approval.status == "approved"


def test_viewer_can_read_but_cannot_approve(client, workspace, review):
    w = workspace
    OrganizationMember.objects.filter(user=w["user"]).update(role="viewer")
    client.force_login(w["user"])
    url = reverse("organizations:email_marketing_review", args=[review.pk])
    assert client.get(url).status_code == 200
    assert client.post(url, {"decision": "approved"}).status_code == 403


@pytest.mark.parametrize("actor_key", ["staff", "admin"])
def test_staff_cannot_decide_on_behalf_of_client(workspace, review, actor_key):
    w = workspace
    with pytest.raises(PermissionDenied):
        services.decide_review(
            actor=w[actor_key], organization=w["org"], approval=review, decision="approved"
        )


@pytest.mark.parametrize("revoke", ["membership", "subscription", "organization"])
def test_revocation_blocks_pending_reviews(client, workspace, review, revoke):
    w = workspace
    if revoke == "membership":
        OrganizationMember.objects.filter(user=w["user"]).update(status="removed")
    elif revoke == "subscription":
        w["subscription"].status = "paused"
        w["subscription"].save()
    else:
        w["org"].status = "suspended"
        w["org"].save()
    client.force_login(w["user"])
    assert (
        client.post(
            reverse("organizations:email_marketing_review", args=[review.pk]),
            {"decision": "approved"},
        ).status_code
        == 403
    )
    review.refresh_from_db()
    assert review.status == "pending"


def test_selected_organization_needs_own_entitlement(client, workspace):
    w = workspace
    other, _ = make_tenant("Other membership")
    make_member(other, w["user"])
    client.force_login(w["user"])
    session = client.session
    session["active_organization_id"] = other.pk
    session.save()
    assert (
        client.get(reverse("organizations:portal_module", args=["email_marketing"])).status_code
        == 403
    )
    assert (
        client.get(reverse("organizations:email_marketing_detail", args=[w["work"].pk])).status_code
        == 403
    )


def test_hidden_work_and_deliverable_urls_are_not_accessible(client, workspace, review):
    w = workspace
    client.force_login(w["user"])
    services.save_deliverable(
        actor=w["staff"],
        organization=w["org"],
        work=w["work"],
        deliverable=w["delivery"],
        expected_revision=1,
        client_visible=False,
    )
    assert (
        client.get(reverse("organizations:email_marketing_review", args=[review.pk])).status_code
        == 404
    )
    assert (
        b"Newsletter proof"
        not in client.get(
            reverse("organizations:email_marketing_detail", args=[w["work"].pk])
        ).content
    )
    services.save_work(
        actor=w["staff"],
        organization=w["org"],
        work=w["work"],
        expected_revision=1,
        client_visible=False,
    )
    assert (
        client.get(reverse("organizations:email_marketing_detail", args=[w["work"].pk])).status_code
        == 404
    )


def test_cross_tenant_urls_and_writes_are_hidden(client, workspace, review):
    w = workspace
    other, outsider = make_tenant("Other reviewer")
    make_subscription(
        other,
        actor=w["admin"],
        service=make_service(
            "Other email", category_slug="other-email", workspace_module="email_marketing"
        ),
    )
    client.force_login(outsider)
    url = reverse("organizations:email_marketing_review", args=[review.pk])
    assert client.get(url).status_code == 404
    assert client.post(url, {"decision": "approved"}).status_code == 404
    assert (
        client.get(reverse("organizations:email_marketing_detail", args=[w["work"].pk])).status_code
        == 404
    )
    client.force_login(w["staff"])
    assert (
        client.get(reverse("staff:email_marketing_workspace", args=[other.slug])).status_code == 404
    )
    with pytest.raises(PermissionDenied):
        services.save_work(
            actor=w["staff"],
            organization=other,
            name="Denied",
            kind="campaign",
            campaign=w["campaign"],
        )


def test_cross_tenant_and_wrong_service_relationships_rejected(workspace):
    w = workspace
    other, _ = make_tenant("Other tenant")
    campaign = make_campaign(other, actor=w["admin"], service_type="email_marketing")
    wrong_service = make_campaign(
        w["org"], actor=w["admin"], service_type="social", name="Wrong service"
    )
    for invalid in [campaign, wrong_service]:
        with pytest.raises(ValidationError):
            services.save_work(
                actor=w["admin"],
                organization=w["org"],
                campaign=invalid,
                name="Bad link",
                kind="newsletter",
            )
    with pytest.raises(ValidationError):
        EmailDeliverable(organization=other, work=w["work"], name="Bad deliverable").full_clean()
    with pytest.raises(ValidationError):
        EmailMetric(
            organization=other,
            work=w["work"],
            recorded_by=w["staff"],
            date=timezone.localdate(),
            source="Report",
            **dict.fromkeys(METRICS, 0),
        ).full_clean()


def test_client_has_no_staff_write_access(client, workspace):
    w = workspace
    client.force_login(w["user"])
    response = client.post(
        reverse("staff:email_marketing_create", args=[w["org"].slug]),
        {"name": "Forbidden", "kind": "newsletter", "campaign": w["campaign"].pk},
    )
    assert response.status_code == 403
    with pytest.raises(PermissionDenied):
        services.save_work(
            actor=w["user"],
            organization=w["org"],
            campaign=w["campaign"],
            name="Forbidden",
            kind="newsletter",
        )
