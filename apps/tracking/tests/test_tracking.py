"""Tests for the agency website tracking domain.

Covers: the closed-taxonomy ingestion endpoint (what a browser can and
cannot report), the never-raises recorder, the two bus subscribers that
make server-recorded events trustworthy, the funnel/traffic selectors,
and the honest-`None` GA4 summary when no reporting connection exists.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from apps.accounts.tests.factories import make_staff, make_super_admin, make_user
from apps.analytics.dateranges import DateRange
from apps.core.events import DomainEvent, bus
from apps.core.ratelimit import RateLimit
from apps.integrations.tests.factories import make_connection
from apps.leads.tests.factories import make_quote_request, make_submission
from apps.tracking import events
from apps.tracking.models import AgencyWebsiteEvent, TrackingSettings
from apps.tracking.policies import can_configure_tracking, can_view_website_analytics
from apps.tracking.selectors import (
    funnel_delta,
    funnel_for,
    ga4_summary_for,
    top_pages_for,
    traffic_sources_for,
)
from apps.tracking.services import record_event
from apps.tracking.tests.factories import make_event

pytestmark = pytest.mark.django_db

RECORD_URL = "/t/event/"


# --- record_event ------------------------------------------------------------


def test_record_event_writes_a_row():
    row = record_event(event_name=events.PAGE_VIEW, path="/services/")
    assert row is not None
    assert AgencyWebsiteEvent.objects.filter(pk=row.pk, path="/services/").exists()


def test_record_event_drops_an_unknown_name():
    assert record_event(event_name="not_a_real_event") is None
    assert not AgencyWebsiteEvent.objects.exists()


def test_record_event_truncates_oversized_fields():
    row = record_event(event_name=events.PAGE_VIEW, path="/" + "x" * 600,
                       context="y" * 300)
    assert len(row.path) == 500
    assert len(row.context) == 200


# --- the ingestion endpoint ----------------------------------------------------


def _post(client, event_name: str, **extra) -> object:
    return client.post(RECORD_URL, data=json.dumps({"event": event_name, **extra}),
                       content_type="application/json")


def test_a_client_reportable_event_is_recorded(client):
    response = _post(client, events.PAGE_VIEW, path="/about/")
    assert response.status_code == 200
    assert AgencyWebsiteEvent.objects.filter(event_name=events.PAGE_VIEW).exists()


@pytest.mark.parametrize("event_name", [
    events.QUOTE_SUBMIT, events.CONTACT_SUBMIT, events.CLIENT_REGISTER,
])
def test_server_only_events_cannot_be_spoofed_through_the_endpoint(client, event_name):
    """`quote_submit`, `contact_submit` and `client_register` are real
    database facts, not browser claims — the endpoint must silently
    refuse to record them even though it returns 200."""
    response = _post(client, event_name)
    assert response.status_code == 200
    assert not AgencyWebsiteEvent.objects.exists()


def test_an_unknown_event_name_is_silently_ignored(client):
    response = _post(client, "made_up_event")
    assert response.status_code == 200
    assert not AgencyWebsiteEvent.objects.exists()


def test_a_malformed_body_is_rejected(client):
    response = client.post(RECORD_URL, data=b"not json",
                           content_type="application/json")
    assert response.status_code == 400


def test_the_endpoint_sets_a_short_lived_session_cookie(client):
    response = _post(client, events.PAGE_VIEW)
    cookie = response.cookies.get("hg_sid")
    assert cookie is not None
    assert cookie["httponly"]
    assert cookie["max-age"] == 30 * 60


def test_repeat_requests_reuse_the_existing_session_cookie(client):
    client.cookies["hg_sid"] = "an-existing-session-value"
    _post(client, events.PAGE_VIEW)
    row = AgencyWebsiteEvent.objects.get()
    from apps.tracking.models import fingerprint_session

    assert row.session_fingerprint == fingerprint_session("an-existing-session-value")


def test_the_endpoint_is_rate_limited_per_ip(client, monkeypatch):
    tight = RateLimit("tracking:event:ip", limit=2, window=timedelta(hours=1))
    monkeypatch.setattr("apps.tracking.views.EVENT_IP_LIMIT", tight)

    assert _post(client, events.PAGE_VIEW).status_code == 200
    assert _post(client, events.PAGE_VIEW).status_code == 200
    blocked = _post(client, events.PAGE_VIEW)
    assert blocked.status_code == 429
    assert AgencyWebsiteEvent.objects.count() == 2


# --- bus subscribers -----------------------------------------------------------


def test_a_contact_submission_records_contact_submit(django_capture_on_commit_callbacks):
    from apps.leads.services import record_submission

    with django_capture_on_commit_callbacks(execute=True):
        make_submission()
        # make_submission() creates the row directly; go through the real
        # service so the bus actually publishes, the same way a visitor's
        # own submission would.
        record_submission(name="Priya", email="priya@vantage.example",
                          message="Help with SEO please.")

    assert AgencyWebsiteEvent.objects.filter(
        event_name=events.CONTACT_SUBMIT).count() == 1


def test_a_quote_request_records_quote_submit(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        make_quote_request()

    assert AgencyWebsiteEvent.objects.filter(
        event_name=events.QUOTE_SUBMIT).exists()


def test_spam_submissions_do_not_record_a_funnel_event(django_capture_on_commit_callbacks):
    """`record_submission` only publishes `lead.submission_received` for
    genuine, non-spam submissions — confirmed here so the funnel cannot be
    inflated by the same spam a human never sees."""
    from apps.leads.services import record_submission

    with django_capture_on_commit_callbacks(execute=True):
        record_submission(name="Spammer", email="spam@example.com",
                          message="buy now", is_spam=True, spam_reason="honeypot")

    assert not AgencyWebsiteEvent.objects.exists()


def test_a_client_registration_records_client_register(django_capture_on_commit_callbacks):
    from apps.accounts.services import register_client

    with django_capture_on_commit_callbacks(execute=True):
        register_client(email="new-client@example.com", password="s3cure-pass-1",
                        full_name="New Client", company_name="Vantage")

    assert AgencyWebsiteEvent.objects.filter(
        event_name=events.CLIENT_REGISTER).exists()


def test_tracking_is_a_real_subscriber_of_the_bus():
    """Guards against a future refactor silently dropping the
    subscription (e.g. an app not importing `services` in `ready()`)."""
    assert bus.handlers_for("lead.submission_received")
    assert bus.handlers_for("account.registered")


def test_an_unrelated_payload_shape_does_not_crash_the_handler():
    """`_on_submission_received` must degrade, not raise, if a future
    caller publishes `lead.submission_received` with an unexpected
    `kind` — never allow a metric handler to break the publisher."""
    bus._dispatch(DomainEvent("lead.submission_received", {"kind": "unknown"}))
    assert not AgencyWebsiteEvent.objects.exists()


# --- selectors -------------------------------------------------------------


def test_funnel_for_counts_each_event_name_in_range():
    today = date(2026, 3, 15)
    make_event(event_name=events.PAGE_VIEW,
              occurred_at=today)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today)
    make_event(event_name=events.SERVICE_VIEW, occurred_at=today)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today - timedelta(days=30))

    date_range = DateRange(key="custom", start=today, end=today, label="Today")
    rows = {row["key"]: row["value"] for row in funnel_for(date_range)}

    assert rows[events.PAGE_VIEW] == 2
    assert rows[events.SERVICE_VIEW] == 1
    assert rows[events.QUOTE_SUBMIT] == 0


def test_funnel_delta_is_none_without_a_comparable_baseline():
    today = date(2026, 3, 15)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today)
    date_range = DateRange(key="custom", start=today, end=today, label="Today")

    rows = {row["key"]: row for row in funnel_delta(date_range)}
    assert rows[events.PAGE_VIEW]["delta_percent"] is None
    assert rows[events.PAGE_VIEW]["value"] == 1


def test_funnel_delta_computes_percentage_change_against_the_previous_period():
    today = date(2026, 3, 15)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today - timedelta(days=1))
    date_range = DateRange(key="custom", start=today, end=today, label="Today")

    rows = {row["key"]: row for row in funnel_delta(date_range)}
    assert rows[events.PAGE_VIEW]["delta_percent"] == 100


def test_traffic_sources_only_counts_page_views_with_a_utm_source():
    today = date(2026, 3, 15)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today, utm_source="google")
    make_event(event_name=events.PAGE_VIEW, occurred_at=today, utm_source="google")
    make_event(event_name=events.PAGE_VIEW, occurred_at=today, utm_source="")
    make_event(event_name=events.SERVICE_VIEW, occurred_at=today, utm_source="meta")

    date_range = DateRange(key="custom", start=today, end=today, label="Today")
    rows = {row["source"]: row["value"] for row in traffic_sources_for(date_range)}

    assert rows == {"google": 2}


def test_top_pages_only_counts_page_views_with_a_path():
    today = date(2026, 3, 15)
    make_event(event_name=events.PAGE_VIEW, occurred_at=today, path="/services/")
    make_event(event_name=events.PAGE_VIEW, occurred_at=today, path="/services/")
    make_event(event_name=events.PAGE_VIEW, occurred_at=today, path="")

    date_range = DateRange(key="custom", start=today, end=today, label="Today")
    rows = {row["path"]: row["value"] for row in top_pages_for(date_range)}

    assert rows == {"/services/": 2}


# --- GA4 honesty -----------------------------------------------------------


def test_ga4_summary_is_none_with_no_connection_at_all():
    date_range = DateRange(key="custom", start=date(2026, 3, 1),
                           end=date(2026, 3, 15), label="")
    assert ga4_summary_for(date_range) is None


def test_ga4_summary_is_none_when_the_connection_is_not_yet_configured():
    make_connection(provider="google_analytics", organization=None)
    date_range = DateRange(key="custom", start=date(2026, 3, 1),
                           end=date(2026, 3, 15), label="")
    assert ga4_summary_for(date_range) is None


def test_ga4_summary_is_none_even_with_a_configured_connection():
    """Honest end-to-end: a connection with credentials still returns
    `None` because no GA4 service-account credential exists in this
    environment — never a fabricated number."""
    make_connection(provider="google_analytics", organization=None,
                    external_account_id="properties/12345", access_token="tok")
    date_range = DateRange(key="custom", start=date(2026, 3, 1),
                           end=date(2026, 3, 15), label="")
    assert ga4_summary_for(date_range) is None


# --- TrackingSettings singleton --------------------------------------------


def test_current_returns_the_same_row_on_every_call():
    first = TrackingSettings.objects.current()
    second = TrackingSettings.objects.current()
    assert first.pk == second.pk == 1


def test_the_settings_row_cannot_be_deleted():
    from django.core.exceptions import ValidationError

    settings_row = TrackingSettings.objects.current()
    with pytest.raises(ValidationError):
        settings_row.delete()


def test_any_tag_configured_is_false_by_default():
    assert TrackingSettings.objects.current().any_tag_configured is False


def test_any_tag_configured_is_true_once_one_id_is_set():
    settings_row = TrackingSettings.objects.current()
    settings_row.ga4_measurement_id = "G-ABC123"
    settings_row.save()
    assert TrackingSettings.objects.current().any_tag_configured is True


# --- policies ----------------------------------------------------------------


def test_super_admin_can_view_website_analytics_and_configure_tracking():
    admin = make_super_admin()
    assert can_view_website_analytics(admin)
    assert can_configure_tracking(admin)


def test_a_client_cannot_view_website_analytics_or_configure_tracking():
    client_user = make_user()
    assert not can_view_website_analytics(client_user)
    assert not can_configure_tracking(client_user)


def test_an_anonymous_actor_cannot_view_website_analytics():
    assert not can_view_website_analytics(None)


def test_a_staff_member_without_the_permission_is_refused():
    staff = make_staff()
    assert not can_view_website_analytics(staff)
    assert not can_configure_tracking(staff)
