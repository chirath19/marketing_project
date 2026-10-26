"""The integrations domain: adapters, sync orchestration, and secrecy.

Three things matter most here, and the tests are organised around them:
a sync must never crash and must always leave a record of what happened;
a provider that is not configured must be reported as such rather than
faked; and a secret must never reach a template, a serializer or another
client.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts.tests.factories import make_user
from apps.integrations.models import (
    AnalyticsSyncRun,
    ConnectionStatus,
    ExternalCampaignReference,
    IntegrationConnection,
    Provider,
    SyncStatus,
)
from apps.integrations.providers.base import ProviderNotConfigured
from apps.integrations.services import map_campaign, run_sync
from apps.integrations.tests.factories import make_connection
from apps.organizations.tests.factories import make_member, make_org
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
def admin():
    return make_super_admin_user("boss@heliograph.agency")


@pytest.fixture
def tenant():
    org = make_org("Vantage Interiors")
    user = make_user(email="priya@vantage.example")
    make_member(org, user)
    return org, user


# ---------------------------------------------------------------------------
# A provider's own scope
# ---------------------------------------------------------------------------


def test_a_client_scoped_provider_needs_an_organization(admin):
    connection = IntegrationConnection(provider=Provider.META_ADS)

    with pytest.raises(ValidationError):
        connection.full_clean()


def test_an_agency_wide_provider_refuses_an_organization(admin, tenant):
    org, _user = tenant
    connection = IntegrationConnection(provider=Provider.RUDDERSTACK,
                                       organization=org)

    with pytest.raises(ValidationError):
        connection.full_clean()


def test_only_one_connection_per_provider_per_client(admin, tenant):
    org, _user = tenant
    make_connection(provider=Provider.META_ADS, organization=org, actor=admin)

    with pytest.raises(ValidationError):
        make_connection(provider=Provider.META_ADS, organization=org, actor=admin)


def test_only_one_agency_wide_connection_per_provider(admin):
    from django.db import IntegrityError, transaction

    make_connection(provider=Provider.RUDDERSTACK, organization=None, actor=admin)

    with pytest.raises(IntegrityError), transaction.atomic():
        IntegrationConnection.objects.create(provider=Provider.RUDDERSTACK,
                                             organization=None)


# ---------------------------------------------------------------------------
# Every adapter reports "not configured" honestly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_key", [
    "meta_ads", "google_ads", "google_analytics", "google_search_console",
    "linkedin_ads", "tiktok_ads",
])
def test_every_adapter_raises_when_unconfigured(admin, tenant, provider_key):
    """No adapter should ever fabricate data — see docs/ANALYTICS.md."""
    from apps.integrations.providers import get_adapter

    org, _user = tenant
    connection = make_connection(provider=provider_key, organization=org,
                                 actor=admin)
    adapter = get_adapter(provider_key)

    with pytest.raises(ProviderNotConfigured):
        adapter.validate_connection(connection)


def test_rudderstack_has_no_analytics_pull_adapter():
    """It only ever routes events outward — see apps/tracking."""
    from apps.integrations.providers import get_adapter

    assert get_adapter(Provider.RUDDERSTACK) is None


# ---------------------------------------------------------------------------
# A sync never crashes, and always leaves a record
# ---------------------------------------------------------------------------


def test_a_sync_with_no_connection_is_recorded_as_skipped(admin, tenant):
    org, _user = tenant

    run = run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    assert run.status == SyncStatus.SKIPPED
    assert run.finished_at is not None
    assert AnalyticsSyncRun.objects.filter(pk=run.pk).exists()


def test_a_sync_with_an_unconfigured_connection_is_skipped_not_crashed(admin,
                                                                       tenant):
    org, _user = tenant
    make_connection(provider=Provider.META_ADS, organization=org, actor=admin)

    run = run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    assert run.status == SyncStatus.SKIPPED
    assert "not" in run.error_summary.lower() or run.error_summary


def test_an_unconfigured_sync_marks_the_connection_not_configured(admin, tenant):
    org, _user = tenant
    connection = make_connection(provider=Provider.META_ADS, organization=org,
                                 actor=admin, external_account_id="123")

    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    connection.refresh_from_db()
    assert connection.status == ConnectionStatus.NOT_CONFIGURED
    assert connection.status_detail


def test_a_sync_for_a_provider_with_no_adapter_is_skipped(admin, tenant):
    org, _user = tenant
    make_connection(provider=Provider.LINKEDIN_ADS, organization=org, actor=admin)

    run = run_sync(provider=Provider.LINKEDIN_ADS, organization=org, actor=admin)

    assert run.status == SyncStatus.SKIPPED


def test_a_sync_failure_notifies_staff_in_app(admin, tenant, monkeypatch):
    """Historical data stays; admin is told; nothing is emailed."""
    from django.core import mail

    from apps.integrations import providers as providers_module
    from apps.notifications.models import Notification

    org, _user = tenant
    make_connection(provider=Provider.META_ADS, organization=org, actor=admin,
                    external_account_id="123", access_token="token")

    class ExplodingAdapter:
        def sync(self, connection, *, start, end):  # noqa: ANN001
            raise RuntimeError("the provider's servers returned a 500")

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: ExplodingAdapter())

    run = run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    assert run.status == SyncStatus.FAILED
    assert Notification.objects.filter(category="integration").exists()
    assert mail.outbox == []


def test_a_failed_sync_does_not_touch_historical_metrics(admin, tenant, monkeypatch):
    """The client dashboard must keep showing what was last synced."""
    from decimal import Decimal

    from apps.campaigns.tests.factories import make_campaign
    from apps.integrations import providers as providers_module
    from apps.integrations.models import ExternalCampaignReference
    from apps.paid_ads.models import DailyAdMetric, Platform

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    connection = make_connection(provider=Provider.META_ADS, organization=org,
                                 actor=admin, external_account_id="123",
                                 access_token="token")
    ExternalCampaignReference.objects.create(
        campaign=campaign, connection=connection, external_campaign_id="ext-1",
    )
    from django.utils import timezone

    DailyAdMetric.objects.create(
        organization=org, campaign=campaign, platform=Platform.META,
        date=timezone.localdate(), currency="USD", spend=Decimal("100"),
        impressions=1000, clicks=10, leads=1, conversions=1,
        revenue=Decimal("0"), source="manual", entry_method="manual",
    )

    class ExplodingAdapter:
        def sync(self, connection, *, start, end):  # noqa: ANN001
            raise RuntimeError("boom")

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: ExplodingAdapter())
    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    assert DailyAdMetric.objects.filter(organization=org).count() == 1


def _mapped_campaign(org, admin):
    from apps.campaigns.tests.factories import make_campaign

    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    connection = make_connection(provider=Provider.META_ADS, organization=org,
                                 actor=admin, external_account_id="123",
                                 access_token="token")
    ExternalCampaignReference.objects.create(
        campaign=campaign, connection=connection, external_campaign_id="ext-1",
    )
    return campaign


class _FakeAdapter:
    """Returns one day of metrics, with a reach/engagements/video_views
    value and one provider-specific overflow number."""

    def __init__(self, spend="150", reach=900, extra_value="42"):
        self.spend, self.reach, self.extra_value = spend, reach, extra_value

    def sync(self, connection, *, start, end):  # noqa: ANN001
        from apps.integrations.providers.base import NormalizedMetrics

        return [NormalizedMetrics(
            external_campaign_id="ext-1", date=start, impressions=1000,
            reach=self.reach, clicks=20, link_clicks=18,
            landing_page_views=15, engagements=30, video_views=50,
            spend=self.spend, leads=2, conversions=1, revenue="300",
            currency="USD", extra={"thruplays": self.extra_value},
        )]


def test_syncing_twice_updates_the_same_row_rather_than_duplicating_it(admin, tenant,
                                                                       monkeypatch):
    """Section 50/TEST 7: idempotent sync, keyed on campaign+platform+date."""
    from apps.integrations import providers as providers_module
    from apps.paid_ads.models import DailyAdMetric

    org, _user = tenant
    campaign = _mapped_campaign(org, admin)

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: _FakeAdapter(spend="150"))
    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: _FakeAdapter(spend="175"))
    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    assert DailyAdMetric.objects.filter(campaign=campaign).count() == 1
    row = DailyAdMetric.objects.get(campaign=campaign)
    assert row.spend == Decimal("175")
    assert row.entry_method == "sync"


def test_a_sync_writes_the_normalized_reach_and_engagement_fields(admin, tenant,
                                                                   monkeypatch):
    from apps.integrations import providers as providers_module
    from apps.paid_ads.models import DailyAdMetric

    org, _user = tenant
    campaign = _mapped_campaign(org, admin)

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: _FakeAdapter())
    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    row = DailyAdMetric.objects.get(campaign=campaign)
    assert row.reach == 900
    assert row.link_clicks == 18
    assert row.landing_page_views == 15
    assert row.engagements == 30
    assert row.video_views == 50


def test_a_sync_stores_provider_specific_overflow_metrics(admin, tenant, monkeypatch):
    from apps.integrations import providers as providers_module
    from apps.integrations.models import ProviderMetric

    org, _user = tenant
    campaign = _mapped_campaign(org, admin)

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: _FakeAdapter(extra_value="42"))
    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    metric = ProviderMetric.objects.get(campaign=campaign, metric_key="thruplays")
    assert metric.numeric_value == Decimal("42")
    assert metric.organization_id == org.pk


def test_resyncing_updates_the_overflow_metric_rather_than_duplicating_it(admin, tenant,
                                                                          monkeypatch):
    from apps.integrations import providers as providers_module
    from apps.integrations.models import ProviderMetric

    org, _user = tenant
    _mapped_campaign(org, admin)

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: _FakeAdapter(extra_value="42"))
    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    monkeypatch.setattr(providers_module, "get_adapter",
                        lambda provider: _FakeAdapter(extra_value="99"))
    run_sync(provider=Provider.META_ADS, organization=org, actor=admin)

    assert ProviderMetric.objects.filter(metric_key="thruplays").count() == 1
    assert ProviderMetric.objects.get(metric_key="thruplays").numeric_value == Decimal("99")


def test_a_provider_metric_cannot_be_moved_to_another_clients_campaign(admin, tenant):
    from apps.campaigns.tests.factories import make_campaign
    from apps.integrations.models import ProviderMetric

    org, _user = tenant
    other = make_org("Northwind Supply")
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")

    metric = ProviderMetric(
        organization=other, campaign=campaign, provider=Provider.META_ADS,
        date="2026-01-01", metric_key="thruplays", numeric_value=Decimal("1"),
    )

    with pytest.raises(ValidationError):
        metric.full_clean()


# ---------------------------------------------------------------------------
# Campaign mapping stays within one client
# ---------------------------------------------------------------------------


def test_a_campaign_cannot_be_mapped_to_another_clients_connection(admin, tenant):
    from apps.campaigns.tests.factories import make_campaign

    org, _user = tenant
    other = make_org("Northwind Supply")
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    theirs = make_connection(provider=Provider.META_ADS, organization=other,
                             actor=admin)

    with pytest.raises(ValidationError):
        map_campaign(campaign=campaign, connection=theirs,
                    external_campaign_id="ext-1", actor=admin)


def test_an_agency_wide_connection_can_be_mapped_to_any_client(admin, tenant):
    """RudderStack-style connections have no one client to clash with."""
    from apps.campaigns.tests.factories import make_campaign

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="paid_ads")
    agency = make_connection(provider=Provider.RUDDERSTACK, organization=None,
                             actor=admin)

    reference = map_campaign(campaign=campaign, connection=agency,
                            external_campaign_id="ext-1", actor=admin)

    assert reference.campaign == campaign


# ---------------------------------------------------------------------------
# Isolation and authorisation
# ---------------------------------------------------------------------------


def test_scoped_staff_cannot_see_another_clients_connection(admin):
    org_a, org_b = make_org("Vantage Interiors"), make_org("Northwind Supply")
    conn_a = make_connection(provider=Provider.META_ADS, organization=org_a,
                             actor=admin)
    conn_b = make_connection(provider=Provider.META_ADS, organization=org_b,
                             actor=admin)

    staff = make_staff_member(
        "specialist@heliograph.agency",
        roles=[make_role("Ads", ["integrations_view", "organizations_view"])],
    )
    assign_client(staff, org_a)

    from apps.integrations import selectors

    visible = {c.pk for c in selectors.visible_connections(staff.user)}
    assert conn_a.pk in visible
    assert conn_b.pk not in visible


def test_a_client_user_is_refused_the_staff_pages(client, tenant):
    org, user = tenant
    sign_in(client, user)

    assert client.get(reverse("staff:module_integrations")).status_code == 403


def test_staff_without_manage_rights_cannot_create_a_connection(tenant):
    org, _user = tenant
    reader = make_staff_member(
        "reader@heliograph.agency",
        roles=[make_role("Reader", ["integrations_view"])],
    )

    with pytest.raises(PermissionDenied):
        from apps.integrations.services import create_connection

        create_connection(provider=Provider.META_ADS, organization=org,
                          actor=reader.user)


def test_an_anonymous_request_to_the_provider_page_is_sent_to_sign_in(client):
    response = client.get(reverse("staff:integration_provider",
                                  args=[Provider.META_ADS]))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url


# ---------------------------------------------------------------------------
# Secrets never reach the surface
# ---------------------------------------------------------------------------


def test_the_provider_page_never_renders_a_raw_token(client, admin, tenant):
    org, _user = tenant
    make_connection(provider=Provider.META_ADS, organization=org, actor=admin,
                    access_token="super-secret-token-value",
                    refresh_token="super-secret-refresh-value",
                    external_account_id="1234567890")
    sign_in(client, admin)

    body = client.get(
        reverse("staff:integration_provider", args=[Provider.META_ADS])
    ).content

    assert b"super-secret-token-value" not in body
    assert b"super-secret-refresh-value" not in body
    # The masked account ID is fine to show.
    assert b"7890" in body


def test_masked_account_id_never_reveals_the_whole_value():
    connection = IntegrationConnection(external_account_id="1234567890")

    assert connection.masked_account_id == "····7890"
    assert "123456" not in connection.masked_account_id


def test_is_configured_is_false_with_no_token():
    connection = IntegrationConnection(external_account_id="123")

    assert not connection.is_configured


# ---------------------------------------------------------------------------
# App-level provider credentials
# ---------------------------------------------------------------------------


def test_staff_can_set_a_providers_app_credentials(client, admin):
    from apps.integrations.credentials import get

    sign_in(client, admin)

    response = client.post(
        reverse("staff:integration_credentials_update", args=[Provider.META_ADS]),
        {"app_id": "123456", "app_secret": "top-secret-value"},
    )

    assert response.status_code == 302
    assert get(Provider.META_ADS, "app_id") == "123456"
    assert get(Provider.META_ADS, "app_secret") == "top-secret-value"


def test_setting_credentials_lets_the_adapter_pass_validation(client, admin, tenant):
    from apps.integrations.providers import get_adapter

    org, _user = tenant
    connection = make_connection(provider=Provider.META_ADS, organization=org,
                                actor=admin, external_account_id="act_1",
                                access_token="tok")
    sign_in(client, admin)

    client.post(
        reverse("staff:integration_credentials_update", args=[Provider.META_ADS]),
        {"app_id": "123456", "app_secret": "top-secret-value"},
    )

    adapter = get_adapter(Provider.META_ADS)
    assert adapter.validate_connection(connection) is True


def test_a_blank_credential_field_leaves_the_stored_value_unchanged(client, admin):
    from apps.integrations.credentials import get

    sign_in(client, admin)
    client.post(
        reverse("staff:integration_credentials_update", args=[Provider.META_ADS]),
        {"app_id": "123456", "app_secret": "top-secret-value"},
    )

    client.post(
        reverse("staff:integration_credentials_update", args=[Provider.META_ADS]),
        {"app_id": "", "app_secret": ""},
    )

    assert get(Provider.META_ADS, "app_id") == "123456"
    assert get(Provider.META_ADS, "app_secret") == "top-secret-value"


def test_the_provider_page_never_shows_a_saved_credential_value(client, admin):
    sign_in(client, admin)
    client.post(
        reverse("staff:integration_credentials_update", args=[Provider.META_ADS]),
        {"app_id": "123456", "app_secret": "top-secret-value"},
    )

    body = client.get(
        reverse("staff:integration_provider", args=[Provider.META_ADS])
    ).content

    assert b"top-secret-value" not in body
    assert b"Configured" in body


def test_the_stored_credential_column_is_ciphertext():
    from django.db import connection as db_connection

    from apps.integrations.models import ProviderCredential

    row = ProviderCredential.objects.create(
        provider=Provider.META_ADS, key="app_secret", value="top-secret-value",
    )
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT value FROM integrations_providercredential WHERE id = %s",
            [row.pk],
        )
        raw = cursor.fetchone()[0]

    assert "top-secret-value" not in raw


def test_a_client_user_cannot_set_provider_credentials(client, tenant):
    _org, user = tenant
    client.force_login(user)

    response = client.post(
        reverse("staff:integration_credentials_update", args=[Provider.META_ADS]),
        {"app_id": "123456", "app_secret": "top-secret-value"},
    )

    assert response.status_code == 403
    from apps.integrations.credentials import get

    assert get(Provider.META_ADS, "app_id") == ""


def test_an_unconfigured_adapter_falls_back_to_a_django_setting(settings):
    from apps.integrations.providers import get_adapter

    settings.META_APP_ID = "env-app-id"
    settings.META_APP_SECRET = "env-app-secret"
    connection = IntegrationConnection(
        provider=Provider.META_ADS, external_account_id="act_1", access_token="tok",
    )

    adapter = get_adapter(Provider.META_ADS)

    assert adapter.validate_connection(connection) is True


def test_rudderstack_has_no_credential_fields_to_configure():
    from apps.integrations.credentials import fields_for

    assert fields_for(Provider.RUDDERSTACK) == []
