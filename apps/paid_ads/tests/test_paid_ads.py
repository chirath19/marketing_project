import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.campaigns.tests.factories import make_campaign
from apps.paid_ads import selectors, services
from apps.paid_ads.forms import FilterForm
from apps.paid_ads.importers import COLUMNS, import_metrics
from apps.paid_ads.models import DailyAdMetric, PaidAdsGoal, Platform

pytestmark = pytest.mark.django_db


def test_daily_grain_upsert_and_provenance(workspace, record):
    first = record()
    correction = record(spend=Decimal("120"))
    record(date=date(2026, 1, 2))
    record(platform="meta")
    assert first.pk == correction.pk
    assert DailyAdMetric.objects.count() == 3
    assert correction.recorded_by == workspace["staff"]
    assert correction.source == "Uploaded platform report"
    assert correction.entry_method == "manual"
    assert correction.spend == 120


@pytest.mark.parametrize("platform", Platform.values)
def test_supported_platforms(record, platform):
    assert record(platform=platform).platform == platform


@pytest.mark.parametrize(
    "invalid",
    [
        {"spend": -1},
        {"revenue": Decimal("NaN")},
        {"clicks": -1},
        {"leads": Decimal("1.2")},
        {"platform": "not-an-ad-platform"},
        {"source": ""},
        {"date": timezone.localdate() + timedelta(days=1)},
        {"spend": Decimal("1.001")},
    ],
)
def test_invalid_observations_are_rejected(record, invalid):
    with pytest.raises(ValidationError):
        record(**invalid)
    assert not DailyAdMetric.objects.exists()


def test_database_rejects_duplicate_daily_key(record):
    observation = record()
    observation.pk = None
    with pytest.raises(IntegrityError), transaction.atomic():
        observation.save(force_insert=True)


def test_ratios_use_summed_numerators_and_denominators(workspace, record, filters):
    record()
    record(
        date=date(2026, 1, 2),
        spend=Decimal("900"),
        revenue=Decimal("900"),
        leads=90,
        clicks=100,
        impressions=9000,
    )
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    assert report["totals"]["spend"] == 1000
    assert report["totals"]["roas"] == Decimal("1.3")
    assert report["totals"]["cpl"] == 10
    assert report["totals"]["ctr"] == 2
    assert report["totals"]["cpc"] == 5
    assert [r["date"] for r in report["daily_rows"]] == [date(2026, 1, 1), date(2026, 1, 2)]
    assert report["campaign_rows"][0]["status"] == "planned"


def test_zero_denominators_and_empty_data_are_distinct(workspace, record, filters):
    empty = selectors.report(workspace["staff"], workspace["org"], filters)
    assert not empty["has_data"]
    record(spend=0, revenue=0, leads=0, clicks=0, impressions=0, conversions=0)
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    assert report["has_data"]
    for ratio in ("roas", "cpl", "ctr", "cpc"):
        assert report["totals"][ratio] is None
        assert report["totals"]["display"][ratio] == "—"


def test_date_platform_campaign_and_currency_filters(workspace, record, filters):
    record()
    record(date=date(2025, 12, 31))
    record(date=date(2026, 2, 1))
    record(platform="meta")
    other = make_campaign(workspace["org"], actor=workspace["admin"], name="Other campaign")
    record(campaign=other)
    euro = make_campaign(workspace["org"], actor=workspace["admin"], name="Euro", currency="EUR")
    record(campaign=euro)
    report = selectors.report(
        workspace["staff"],
        workspace["org"],
        {
            **filters,
            "platform": "google",
            "campaign": workspace["campaign"],
        },
    )
    assert report["totals"]["records"] == 1
    assert report["totals"]["spend"] == 100
    all_usd = selectors.report(workspace["staff"], workspace["org"], filters)
    assert all_usd["totals"]["records"] == 3
    eur = selectors.report(workspace["staff"], workspace["org"], {**filters, "currency": "EUR"})
    assert eur["totals"]["spend"] == 100


def test_currency_snapshot_survives_campaign_change(workspace, record):
    row = record()
    workspace["campaign"].currency = "EUR"
    workspace["campaign"].save(update_fields=["currency"])
    assert record().currency == row.currency == "USD"
    assert record(date=date(2026, 1, 2)).currency == "EUR"


def test_goals_use_their_own_period_and_scope(workspace, record, filters):
    record()
    record(date=date(2026, 1, 2), spend=900, leads=90)
    record(platform="meta", leads=1000)
    goal = services.save_goal(
        organization=workspace["org"],
        actor=workspace["staff"],
        title="January Google leads",
        metric="leads",
        target=100,
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 31),
        currency="USD",
        platform="google",
        campaign=workspace["campaign"],
    )
    report = selectors.report(
        workspace["staff"],
        workspace["org"],
        {
            **filters,
            "end": date(2026, 1, 1),
            "platform": "google",
        },
    )
    assert report["totals"]["leads"] == 10
    assert report["goals"][0]["current"] == "100"
    assert report["goals"][0]["assessment"] == "Target reached"
    services.save_goal(
        organization=workspace["org"], actor=workspace["staff"], goal=goal, is_active=False
    )
    assert not selectors.report(workspace["staff"], workspace["org"], filters)["goals"]


@pytest.mark.parametrize(
    ("metric", "target", "expected"),
    [
        ("spend", 200, "Within ceiling so far"),
        ("spend", 50, "Above ceiling"),
        ("cpl", 5, "Above ceiling"),
        ("roas", 3, "Target reached"),
    ],
)
def test_goal_direction(workspace, record, filters, metric, target, expected):
    record()
    services.save_goal(
        organization=workspace["org"],
        actor=workspace["staff"],
        title="Target",
        metric=metric,
        target=target,
        starts_on=filters["start"],
        ends_on=filters["end"],
        currency="USD",
    )
    result = selectors.report(workspace["staff"], workspace["org"], filters)
    assert result["goals"][0]["assessment"] == expected


def test_empty_goal_never_claims_success(workspace, filters):
    services.save_goal(
        organization=workspace["org"],
        actor=workspace["staff"],
        title="Spend",
        metric="spend",
        target=100,
        starts_on=filters["start"],
        ends_on=filters["end"],
        currency="USD",
    )
    result = selectors.report(workspace["staff"], workspace["org"], filters)
    assert result["goals"][0]["assessment"] == "No data"


def csv_file(workspace, *lines):
    default = f"2026-01-01,{workspace['campaign'].pk},Google,100,1000,100,10,5,400"
    return io.BytesIO((",".join(COLUMNS) + "\n" + "\n".join(lines or [default])).encode())


def test_csv_reimport_is_idempotent(workspace):
    for _ in range(2):
        assert (
            import_metrics(
                actor=workspace["staff"],
                organization=workspace["org"],
                file_obj=csv_file(workspace),
                source="Google export",
            )
            == 1
        )
    row = DailyAdMetric.objects.get()
    assert row.entry_method == "csv"
    assert row.spend == 100


@pytest.mark.parametrize(
    "bad",
    [
        "nan",
        "Infinity",
        "-1",
        "hello",
        "",
        "1.234",
        "1e99999",
    ],
)
def test_bad_csv_rolls_back_previous_rows(workspace, bad):
    first = f"2026-01-01,{workspace['campaign'].pk},google,100,1000,100,10,5,400"
    second = f"2026-01-02,{workspace['campaign'].pk},google,{bad},1000,100,10,5,400"
    with pytest.raises(ValidationError):
        import_metrics(
            actor=workspace["staff"],
            organization=workspace["org"],
            file_obj=csv_file(workspace, first, second),
            source="Report",
        )
    assert not DailyAdMetric.objects.exists()


@pytest.mark.parametrize(
    "content",
    [
        b"wrong,header\n1,2",
        b"\xff\xfe",
        b"",
        ",".join(COLUMNS).encode(),
    ],
)
def test_malformed_csv_is_reported(workspace, content):
    with pytest.raises(ValidationError):
        import_metrics(
            actor=workspace["staff"],
            organization=workspace["org"],
            file_obj=io.BytesIO(content),
            source="Report",
        )


def test_csv_duplicate_and_extra_columns_are_rejected(workspace):
    line = f"2026-01-01,{workspace['campaign'].pk},google,100,1000,100,10,5,400"
    for lines in [(line, line), (line + ",unexpected",)]:
        with pytest.raises(ValidationError):
            import_metrics(
                actor=workspace["staff"],
                organization=workspace["org"],
                file_obj=csv_file(workspace, *lines),
                source="Report",
            )
    assert not DailyAdMetric.objects.exists()


def test_filter_errors_do_not_silently_widen_report(workspace):
    for data in [
        {"start": "bad"},
        {"start": "2026-01-02", "end": "2026-01-01"},
        {"start": "2020-01-01", "end": "2026-01-01"},
        {"platform": "unknown"},
    ]:
        assert not FilterForm(
            data, actor=workspace["staff"], organization=workspace["org"]
        ).is_valid()


def test_staff_manual_entry_correction_and_import_pages(client, workspace):
    client.force_login(workspace["staff"])
    url = reverse("staff:paid_ads_record", args=[workspace["org"].slug])
    payload = {
        "date": "2026-01-01",
        "campaign": workspace["campaign"].pk,
        "platform": "google",
        "source": "Report",
        "spend": "100",
        "impressions": 1000,
        "clicks": 100,
        "leads": 10,
        "conversions": 5,
        "revenue": 400,
    }
    assert client.get(url).status_code == 200
    for spend in (100, 120):
        response = client.post(url, {**payload, "spend": spend})
        assert response.status_code == 302, response.content.decode()
    assert DailyAdMetric.objects.get().spend == 120
    upload = SimpleUploadedFile("report.csv", csv_file(workspace).read(), content_type="text/csv")
    response = client.post(
        reverse("staff:paid_ads_import", args=[workspace["org"].slug]),
        {"file": upload, "source": "Platform export"},
    )
    assert response.status_code == 302
    assert DailyAdMetric.objects.get().spend == 100


def test_workspace_renders_real_data_without_template_leaks(client, workspace, record):
    record()
    for user, url in [
        (workspace["staff"], reverse("staff:paid_ads_workspace", args=[workspace["org"].slug])),
        (workspace["user"], reverse("organizations:portal_module", args=["paid_ads"])),
    ]:
        client.force_login(user)
        response = client.get(url, {"start": "2026-01-01", "end": "2026-01-31"})
        assert response.status_code == 200
        body = response.content.decode()
        for expected in [
            "USD 100.00",
            "4.00×",
            "10.00%",
            "Daily performance",
            "Google",
            "No advertising-platform connection has been synced",
        ]:
            assert expected in body
        assert "{{" not in body and "{%" not in body
        assert ("Record a day" in body) == user.is_staff_member


def test_invalid_form_retains_errors_and_creates_nothing(client, workspace):
    client.force_login(workspace["staff"])
    response = client.post(
        reverse("staff:paid_ads_record", args=[workspace["org"].slug]), {"source": "Missing values"}
    )
    assert response.status_code == 400
    assert not DailyAdMetric.objects.exists()


def test_goal_forms_create_update_and_deactivate(client, workspace):
    client.force_login(workspace["staff"])
    values = {
        "title": "Leads target",
        "metric": "leads",
        "target": "100",
        "starts_on": "2026-01-01",
        "ends_on": "2026-01-31",
        "currency": "USD",
        "platform": "google",
        "campaign": workspace["campaign"].pk,
        "is_active": "on",
    }
    response = client.post(
        reverse("staff:paid_ads_goal_create", args=[workspace["org"].slug]), values
    )
    assert response.status_code == 302, response.content.decode()
    goal = PaidAdsGoal.objects.get()
    values.pop("is_active")
    response = client.post(
        reverse("staff:paid_ads_goal_edit", args=[workspace["org"].slug, goal.pk]), values
    )
    assert response.status_code == 302
    goal.refresh_from_db()
    assert not goal.is_active


# ---------------------------------------------------------------------------
# New normalized measures (section 11)
# ---------------------------------------------------------------------------


def test_optional_measures_default_to_unreported_not_zero(record):
    observation = record()
    assert observation.reach is None
    assert observation.link_clicks is None
    assert observation.video_views is None


def test_optional_measures_can_be_recorded(record):
    observation = record(reach=5000, link_clicks=80, landing_page_views=60,
                         engagements=200, video_views=300)
    assert observation.reach == 5000
    assert observation.engagements == 200


def test_cpm_cpa_and_engagement_rate_are_calculated(workspace, record, filters):
    record(spend=Decimal("100"), impressions=10000, conversions=5,
          reach=1000, engagements=50)
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    assert report["totals"]["cpm"] == Decimal("10")
    assert report["totals"]["cpa"] == Decimal("20")
    assert report["totals"]["engagement_rate"] == Decimal("5")


def test_a_ratio_with_an_unreported_denominator_is_unavailable(workspace, record, filters):
    """Reach was never entered for this observation — `frequency` and
    `engagement_rate` must read "unavailable," never a fabricated
    zero-based ratio."""
    record(reach=None, engagements=None)
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    assert report["totals"]["frequency"] is None
    assert report["totals"]["engagement_rate"] is None
    assert report["totals"]["display"]["frequency"] == "—"


# ---------------------------------------------------------------------------
# Objective-aware reporting (sections 4 and 10)
# ---------------------------------------------------------------------------


def test_a_campaign_with_no_detail_gets_the_default_kpi_order(workspace, record, filters):
    filters = {**filters, "campaign": workspace["campaign"]}
    record()
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    assert [kpi["key"] for kpi in report["kpis"]] == list(selectors.DEFAULT_PRIORITY)


def test_an_awareness_campaign_leads_with_reach_not_clicks(workspace, record, filters):
    from apps.paid_ads.models import CampaignObjective, PaidAdsCampaignDetail

    PaidAdsCampaignDetail.objects.create(
        campaign=workspace["campaign"], platform="meta",
        objective=CampaignObjective.AWARENESS,
    )
    filters = {**filters, "campaign": workspace["campaign"]}
    record(reach=5000)
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    keys = [kpi["key"] for kpi in report["kpis"]]
    assert keys[:2] == ["spend", "reach"]
    assert "clicks" not in keys


def test_a_lead_generation_campaign_leads_with_leads_and_cpl(workspace, record, filters):
    from apps.paid_ads.models import CampaignObjective, PaidAdsCampaignDetail

    PaidAdsCampaignDetail.objects.create(
        campaign=workspace["campaign"], platform="google",
        objective=CampaignObjective.LEAD_GENERATION,
    )
    filters = {**filters, "campaign": workspace["campaign"]}
    record()
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    assert [kpi["key"] for kpi in report["kpis"]] == ["spend", "leads", "cpl", "conversions"]


def test_the_campaign_type_registry_resolves_the_paid_ads_detail_model():
    from apps.campaigns.registry import detail_model_for
    from apps.paid_ads.models import PaidAdsCampaignDetail

    assert detail_model_for("paid_ads") is PaidAdsCampaignDetail


def test_a_paid_ads_detail_cannot_be_read_through_a_different_clients_campaign(workspace):
    """Isolation is inherited, not re-implemented: a detail row has no
    organization of its own — it is reached only through its campaign,
    which `OrganizationOwnedModel` already scopes."""
    from apps.organizations.tests.factories import make_tenant
    from apps.paid_ads.models import PaidAdsCampaignDetail

    PaidAdsCampaignDetail.objects.create(campaign=workspace["campaign"], platform="meta")
    other_org, other_user = make_tenant("Other client")

    from apps.campaigns import selectors as campaign_selectors

    assert campaign_selectors.client_campaign(other_user, workspace["campaign"].pk) is None


# ---------------------------------------------------------------------------
# Period-over-period comparison (section 19)
# ---------------------------------------------------------------------------


def test_a_comparison_is_shown_against_a_period_with_real_history(workspace, record, filters):
    record(date=date(2025, 12, 15), spend=Decimal("100"), impressions=1000)
    record(date=date(2026, 1, 15), spend=Decimal("150"), impressions=1000)
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    spend_kpi = next(kpi for kpi in report["kpis"] if kpi["key"] == "spend")
    assert spend_kpi["delta_percent"] == 50
    assert spend_kpi["direction"] == "good"


def test_no_comparison_is_shown_without_a_previous_period(workspace, record, filters):
    record(date=date(2026, 1, 15), spend=Decimal("150"))
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    spend_kpi = next(kpi for kpi in report["kpis"] if kpi["key"] == "spend")
    assert spend_kpi["delta_percent"] is None
    assert spend_kpi["direction"] == "neutral"


def test_a_rising_cost_metric_is_shown_as_a_regression_not_an_improvement(workspace, record,
                                                                          filters):
    """CPL going up is worse, not better — the arrow must say so even
    though the raw number rose."""
    from apps.paid_ads.models import CampaignObjective, PaidAdsCampaignDetail

    PaidAdsCampaignDetail.objects.create(
        campaign=workspace["campaign"], platform="google",
        objective=CampaignObjective.LEAD_GENERATION,
    )
    record(date=date(2025, 12, 15), spend=Decimal("100"), leads=10)
    record(date=date(2026, 1, 15), spend=Decimal("200"), leads=10)
    filters = {**filters, "campaign": workspace["campaign"]}
    report = selectors.report(workspace["staff"], workspace["org"], filters)
    cpl_kpi = next(kpi for kpi in report["kpis"] if kpi["key"] == "cpl")
    assert cpl_kpi["delta_percent"] == 100
    assert cpl_kpi["direction"] == "bad"
