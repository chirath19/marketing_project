"""Workflow journeys keep existing role, feature, company and recipient boundaries."""

import pytest
from django.urls import reverse

from apps.analytics.services import create_report
from apps.core import operations
from apps.core.workflow import client_navigation, staff_navigation
from apps.organizations.tests.factories import make_member, make_tenant, make_user
from apps.staff.services import create_staff_account
from apps.staff.tests.factories import (
    assign_client,
    make_role,
    make_staff_member,
    make_super_admin_user,
)
from apps.subscriptions.tests.factories import make_subscription

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace():
    admin = make_super_admin_user()
    owner = create_staff_account(
        actor=admin, email="workflow-owner@example.com", account_type="system_owner"
    ).user
    org, customer = make_tenant("Workflow client")
    colleague = make_user("colleague@example.com")
    make_member(org, colleague)
    project = make_subscription(org, actor=admin)
    report = create_report(
        actor=admin,
        organization=org,
        client=customer,
        subscription=project,
        title="Launch milestones",
        summary="First stage done",
        progress=35,
        publish=True,
    )
    create_report(
        actor=admin,
        organization=org,
        client=colleague,
        subscription=project,
        title="Private colleague report",
        summary="Private",
        progress=70,
        publish=True,
    )
    create_report(
        actor=admin,
        organization=org,
        client=customer,
        subscription=project,
        title="Unpublished draft",
        summary="Staff only",
        progress=80,
    )
    return admin, owner, org, customer, colleague, project, report


@pytest.mark.parametrize("role", ["admin", "owner"])
def test_staff_primary_navigation_and_every_hub_renders(client, workspace, role):
    admin, owner, org, customer, _, project, _ = workspace
    actor = admin if role == "admin" else owner
    client.force_login(actor)
    links = staff_navigation(actor)
    assert [item["key"] for item in links] == [
        "dashboard",
        "clients",
        "requests",
        "projects",
        "messages",
        "payments",
        "website",
        "administration",
    ]
    for link in links:
        response = client.get(link["href"])
        assert response.status_code == 200, link
    assert client.get(reverse("staff:client_detail", args=[org.slug])).status_code == 200
    assert client.get(reverse("staff:subscription_detail", args=[project.pk])).status_code == 200
    admin_page = client.get(reverse("staff:workflow", args=["administration"]))
    assert (b'href="/staff/settings/"' in admin_page.content) == (role == "admin")


def test_client_has_six_plain_navigation_items_with_legacy_pages_grouped(client, workspace):
    _, _, org, customer, _, project, _ = workspace
    client.force_login(customer)
    links = client_navigation(customer, org, "seo")
    assert [item["key"] for item in links] == [
        "overview",
        "requests",
        "projects",
        "messages",
        "payments",
        "account",
    ]
    assert next(item for item in links if item["active"])["key"] == "projects"
    for link in links:
        assert client.get(link["href"]).status_code == 200, link
    response = client.get(reverse("organizations:service_detail", args=[project.pk]))
    assert b"Launch milestones" in response.content
    assert b"Private colleague report" not in response.content
    assert b"Unpublished draft" not in response.content
    assert b'value="35"' in response.content


def test_contact_selection_does_not_mix_private_records(client, workspace):
    admin, _, org, customer, colleague, _, _ = workspace
    client.force_login(admin)
    path = reverse("staff:client_detail", args=[org.slug])
    page = client.get(path, {"client": customer.pk})
    assert b"Launch milestones" in page.content
    assert b"Private colleague report" not in page.content
    page = client.get(path, {"client": colleague.pk})
    assert b"Private colleague report" in page.content
    assert b"Launch milestones" not in page.content
    _, outsider = make_tenant("Outside")
    assert client.get(path, {"client": outsider.pk}).status_code == 404


def test_restricted_staff_hubs_and_clients_stay_scoped(client, workspace):
    _, _, org, _, _, project, _ = workspace
    role = make_role("Workflow reporting", ["organizations_view", "analytics_view"])
    staff = make_staff_member(roles=[role])
    assign_client(staff, org)
    other_org, _ = make_tenant("Unassigned company")
    client.force_login(staff.user)
    assert client.get(reverse("staff:workflow", args=["projects"])).status_code == 200
    assert client.get(reverse("staff:workflow", args=["payments"])).status_code == 403
    assert client.get(reverse("staff:workflow", args=["requests"])).status_code == 404
    assert client.get(reverse("staff:client_detail", args=[other_org.slug])).status_code in {
        403,
        404,
    }
    page = client.get(reverse("staff:client_detail", args=[org.slug]))
    assert b"Launch milestones" in page.content
    assert f'href="/staff/subscriptions/{project.pk}/"'.encode() not in page.content


def test_disabled_features_do_not_reappear_in_new_navigation_or_projects(client, workspace):
    admin, owner, org, customer, _, project, _ = workspace
    operations.update(
        actor=admin,
        values={
            "feature_flags": {
                "messages": False,
                "reports": False,
                "payments": False,
                "approvals": False,
                "seo": False,
            }
        },
    )
    client.force_login(customer)
    response = client.get(reverse("organizations:service_detail", args=[project.pk]))
    assert response.status_code == 200
    assert b"Launch milestones" not in response.content
    assert b'href="/organization/area/seo/"' not in response.content
    assert b'href="/organization/messages/' not in response.content
    client.force_login(owner)
    page = client.get(reverse("staff:workflow", args=["payments"]))
    assert page.status_code in {403, 404}


def test_project_message_context_is_prefilled_and_cannot_cross_company(client, workspace):
    admin, _, _, customer, _, project, _ = workspace
    other_org, _ = make_tenant("Other project client")
    other_project = make_subscription(other_org, actor=admin)
    client.force_login(customer)
    path = reverse("organizations:client_desk")
    page = client.get(path, {"project": project.pk})
    assert page.status_code == 200
    assert page.context["message_form"].initial["subscription"] == project.pk
    assert client.get(path, {"project": other_project.pk}).status_code == 404


def test_selected_company_controls_project_navigation_and_details(client, workspace):
    _, _, _, customer, _, project, _ = workspace
    other_org, _ = make_tenant("Second membership")
    make_member(other_org, customer)
    client.force_login(customer)
    client.post(reverse("organizations:switch"), {"organization": other_org.pk})
    assert client.get(reverse("organizations:service_detail", args=[project.pk])).status_code == 404
    page = client.get(reverse("organizations:services"))
    assert project not in page.context["active"]


def test_project_billing_includes_quote_records_without_exposing_other_contacts(client, workspace):
    from decimal import Decimal

    from django.utils import timezone

    from apps.leads.tests.factories import make_quote_request
    from apps.subscriptions import invoices, receipts

    admin, _, org, customer, colleague, project, _ = workspace
    quote = make_quote_request(organization=org, submitted_by=customer, email=customer.email)
    project.quote = quote
    project.save(update_fields=["quote"])
    values = {
        "amount": Decimal("100"),
        "currency": "USD",
        "issued_on": timezone.localdate(),
        "due_on": timezone.localdate(),
        "description": "Project work",
        "publish": True,
    }
    invoice = invoices.create(
        actor=admin,
        organization=org,
        client=customer,
        reference="OWN-QUOTE-INVOICE",
        quote=quote,
        **values,
    )
    invoices.create(
        actor=admin,
        organization=org,
        client=colleague,
        reference="PRIVATE-COLLEAGUE-INVOICE",
        subscription=project,
        **values,
    )
    receipts.issue(
        actor=admin,
        organization=org,
        client=customer,
        invoice=invoice,
        reference="OWN-QUOTE-RECEIPT",
        description="Confirmed payment",
        amount=Decimal("50"),
        currency="USD",
        paid_on=timezone.localdate(),
        payment_method="Bank transfer",
    )
    client.force_login(customer)
    page = client.get(reverse("organizations:service_detail", args=[project.pk]))
    assert b"OWN-QUOTE-INVOICE" in page.content
    assert b"OWN-QUOTE-RECEIPT" in page.content
    assert b"PRIVATE-COLLEAGUE-INVOICE" not in page.content
