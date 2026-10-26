"""The SEO module.

Isolation has its own file. This one is about the module itself: that it
extends the campaign engine rather than duplicating it, that figures are
counted from records and never invented, and that the CSV import is
strict about meaning while forgiving about shape.
"""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import make_user
from apps.organizations.tests.factories import make_member, make_org
from apps.seo import selectors, services
from apps.seo.importers import import_keyword_positions
from apps.seo.models import (
    AuditStatus,
    BacklinkStatus,
    IssueSeverity,
    IssueStatus,
    Keyword,
    KeywordRanking,
    TaskStatus,
)
from apps.seo.tests.factories import (
    make_audit,
    make_backlink,
    make_goal,
    make_issue,
    make_keyword,
    make_position,
    make_task,
)
from apps.staff.tests.factories import (
    PASSWORD,
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
# It extends the campaign engine rather than duplicating it
# ---------------------------------------------------------------------------


def test_seo_registers_itself_with_the_campaign_engine():
    """The architectural point of the previous phase, proved by the
    first module to use it."""
    from apps.campaigns.registry import get_type

    seo = get_type("seo")

    assert seo is not None
    assert seo.detail_model == "apps.seo.models.SeoCampaignDetail"
    assert seo.goal_label == "Target positions"


def test_an_seo_campaign_is_an_ordinary_campaign(admin, tenant):
    """No parallel campaign table: an SEO campaign has the same status
    machine, owner and isolation as every other."""
    from apps.campaigns.models import Campaign
    from apps.campaigns.tests.factories import make_campaign

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, name="Spring search push",
                             service_type="seo")

    assert Campaign.objects.filter(pk=campaign.pk).exists()
    assert campaign.objective_label == "Target positions"


def test_the_detail_record_attaches_to_a_shared_campaign(admin, tenant):
    from apps.campaigns.tests.factories import make_campaign
    from apps.seo.models import SeoCampaignDetail

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="seo")

    SeoCampaignDetail.objects.create(
        campaign=campaign, focus="Range pages\nLocation pages",
        competitors="rival.example",
    )
    campaign.refresh_from_db()

    assert campaign.detail is not None
    assert campaign.detail.focus_lines == ["Range pages", "Location pages"]
    assert campaign.detail.competitor_lines == ["rival.example"]


def test_a_progress_update_is_a_campaign_event(admin, tenant):
    """SEO does not grow a second timeline with its own leak risk."""
    from apps.campaigns.tests.factories import make_campaign

    org, _user = tenant
    campaign = make_campaign(org, actor=admin, service_type="seo")

    entry = services.post_progress_update(
        campaign=campaign, body="Three fixes shipped this week.", actor=admin,
    )

    assert entry in campaign.events.all()
    assert not entry.is_internal, "a progress update is for the client"


# ---------------------------------------------------------------------------
# Audits
# ---------------------------------------------------------------------------


def test_an_audit_starts_internal(admin, tenant):
    org, _user = tenant
    audit = make_audit(org, actor=admin)

    assert audit.status == AuditStatus.IN_PROGRESS
    assert not audit.is_delivered


def test_an_audit_cannot_be_delivered_without_a_summary(admin, tenant):
    """The summary is the part the client reads."""
    org, _user = tenant
    audit = make_audit(org, actor=admin)

    with pytest.raises(ValidationError):
        services.deliver_audit(audit=audit, actor=admin)


def test_delivering_an_audit_needs_its_own_right(tenant):
    org, _user = tenant
    admin = make_super_admin_user("setup@heliograph.agency")
    audit = make_audit(org, actor=admin, summary="Readable.")

    editor = make_staff_member(
        "editor@heliograph.agency",
        roles=[make_role("Editor", ["seo_view", "seo_edit"])],
    )

    with pytest.raises(PermissionDenied):
        services.deliver_audit(audit=audit, actor=editor.user)


def test_delivering_an_audit_tells_the_client_in_app(admin, tenant):
    from apps.notifications.models import Notification

    org, user = tenant
    audit = make_audit(org, actor=admin, summary="Three things to fix.")
    services.deliver_audit(audit=audit, actor=admin)

    assert Notification.objects.filter(recipient=user, category="seo").exists()
    assert mail.outbox == [], "nothing is emailed"


def test_findings_are_ordered_worst_first(admin, tenant):
    """Severity is a string in the database; alphabetical order would put
    critical after high and below low."""
    org, _user = tenant
    audit = make_audit(org, actor=admin)
    make_issue(audit, actor=admin, title="Low one", severity=IssueSeverity.LOW)
    make_issue(audit, actor=admin, title="Critical one",
               severity=IssueSeverity.CRITICAL)
    make_issue(audit, actor=admin, title="Medium one",
               severity=IssueSeverity.MEDIUM)

    titles = [issue.title for issue in selectors.issues_for(audit)]

    assert titles == ["Critical one", "Medium one", "Low one"]


def test_fixing_a_finding_stamps_the_date(admin, tenant):
    org, _user = tenant
    issue = make_issue(make_audit(org, actor=admin), actor=admin)

    services.set_issue_status(issue=issue, status=IssueStatus.FIXED, actor=admin)

    issue.refresh_from_db()
    assert issue.resolved_on == timezone.localdate()


def test_reopening_a_finding_clears_the_date(admin, tenant):
    """Otherwise "fixed on" would contradict the status beside it."""
    org, _user = tenant
    issue = make_issue(make_audit(org, actor=admin), actor=admin)
    services.set_issue_status(issue=issue, status=IssueStatus.FIXED, actor=admin)

    services.set_issue_status(issue=issue, status=IssueStatus.OPEN, actor=admin)

    issue.refresh_from_db()
    assert issue.resolved_on is None


# ---------------------------------------------------------------------------
# Keywords and positions
# ---------------------------------------------------------------------------


def test_the_same_term_cannot_be_tracked_twice_for_one_client(admin, tenant):
    """Two rows would split one history in two and make every chart
    wrong."""
    org, _user = tenant
    make_keyword(org, actor=admin, term="interior designer")

    with pytest.raises(ValidationError):
        services.add_keyword(organization=org, term="interior designer",
                             actor=admin)


def test_two_clients_can_track_the_same_term(admin):
    org_a, org_b = make_org("Vantage"), make_org("Northwind")
    make_keyword(org_a, actor=admin, term="sofas")
    make_keyword(org_b, actor=admin, term="sofas")

    assert Keyword.objects.filter(term="sofas").count() == 2


def test_a_second_reading_for_one_day_replaces_the_first(admin, tenant):
    """Otherwise the charts would have to choose between them."""
    org, _user = tenant
    keyword = make_keyword(org, actor=admin)
    today = timezone.localdate()

    make_position(keyword, position=9, recorded_on=today)
    make_position(keyword, position=7, recorded_on=today)

    assert keyword.rankings.count() == 1
    assert keyword.rankings.first().position == 7


def test_a_blank_position_means_not_ranking_not_zero(admin, tenant):
    org, _user = tenant
    keyword = make_keyword(org, actor=admin)

    services.record_position(keyword=keyword, actor=admin,
                             recorded_on=timezone.localdate(), position=None)

    reading = keyword.rankings.first()
    assert reading.position is None


def test_history_reads_oldest_first(admin, tenant):
    """A chart reads left to right; the model orders newest first because
    a list reads top down."""
    org, _user = tenant
    keyword = make_keyword(org, actor=admin)
    today = timezone.localdate()
    make_position(keyword, position=20, recorded_on=today - timedelta(days=14))
    make_position(keyword, position=9, recorded_on=today)

    history = selectors.ranking_history(keyword)

    assert [reading.position for reading in history] == [20, 9]


# ---------------------------------------------------------------------------
# Figures are counted, never invented
# ---------------------------------------------------------------------------


def test_the_summary_counts_only_what_is_recorded(admin, tenant):
    org, _user = tenant
    ranked = make_keyword(org, actor=admin, term="ranked term")
    make_keyword(org, actor=admin, term="unranked term")
    make_position(ranked, position=4)

    summary = selectors.summary_for(org)

    assert summary["keywords_tracked"] == 2
    assert summary["keywords_ranked"] == 1
    assert summary["keywords_top_10"] == 1
    assert summary["keywords_top_3"] == 0


def test_the_average_ignores_terms_with_no_reading(admin, tenant):
    """Counting an unranked term as a large number would drag the
    average toward a figure nobody measured."""
    org, _user = tenant
    first = make_keyword(org, actor=admin, term="one")
    second = make_keyword(org, actor=admin, term="two")
    make_keyword(org, actor=admin, term="never checked")
    make_position(first, position=4)
    make_position(second, position=6)

    assert selectors.summary_for(org)["average_position"] == 5.0


def test_the_average_is_none_when_nothing_has_been_measured(admin, tenant):
    org, _user = tenant
    make_keyword(org, actor=admin)

    assert selectors.summary_for(org)["average_position"] is None


def test_goal_progress_is_measured_not_typed(admin, tenant):
    """A goal whose progress is entered by hand is a goal nobody has to
    meet."""
    org, _user = tenant
    make_goal(org, metric="top_10", target=2)
    first = make_keyword(org, actor=admin, term="one")
    second = make_keyword(org, actor=admin, term="two")
    make_position(first, position=3)

    [row] = selectors.goals_for(org)
    assert row["current"] == 1
    assert not row["met"]

    make_position(second, position=8)

    [row] = selectors.goals_for(org)
    assert row["current"] == 2
    assert row["met"]


def test_a_goal_of_zero_is_refused(tenant):
    from apps.seo.models import SeoGoal

    org, _user = tenant
    goal = SeoGoal(organization=org, metric="top_10", target=0)

    with pytest.raises(ValidationError):
        goal.full_clean()


def test_has_any_data_decides_between_a_workspace_and_an_empty_state(admin,
                                                                     tenant):
    org, _user = tenant
    assert not selectors.has_any_data(org)

    make_keyword(org, actor=admin)

    assert selectors.has_any_data(org)


# ---------------------------------------------------------------------------
# Work and links
# ---------------------------------------------------------------------------


def test_a_finished_task_with_a_link_is_a_deliverable(admin, tenant):
    org, _user = tenant
    task = make_task(org, actor=admin, status=TaskStatus.DONE,
                     delivered_url="https://example.com/new-page")

    assert task.is_deliverable


def test_a_finished_task_with_no_link_is_not_a_deliverable(admin, tenant):
    """The client has to be able to see the thing."""
    org, _user = tenant
    task = make_task(org, actor=admin, status=TaskStatus.DONE)

    assert not task.is_deliverable


def test_completing_a_task_stamps_the_date(admin, tenant):
    org, _user = tenant
    task = make_task(org, actor=admin)

    services.update_task(task=task, actor=admin, status=TaskStatus.DONE)

    task.refresh_from_db()
    assert task.completed_on == timezone.localdate()


def test_reopening_a_task_clears_the_completion_date(admin, tenant):
    org, _user = tenant
    task = make_task(org, actor=admin, status=TaskStatus.DONE)
    services.update_task(task=task, actor=admin, status=TaskStatus.DONE)

    services.update_task(task=task, actor=admin, status=TaskStatus.IN_PROGRESS)

    task.refresh_from_db()
    assert task.completed_on is None


def test_an_overdue_task_is_flagged(admin, tenant):
    org, _user = tenant
    task = make_task(org, actor=admin,
                     due_on=timezone.localdate() - timedelta(days=1))

    assert task.is_overdue


def test_marking_a_link_live_stamps_the_date(admin, tenant):
    org, _user = tenant
    link = make_backlink(org, actor=admin)

    services.update_backlink(backlink=link, actor=admin,
                             status=BacklinkStatus.LIVE)

    link.refresh_from_db()
    assert link.went_live_on == timezone.localdate()


# ---------------------------------------------------------------------------
# The CSV import
# ---------------------------------------------------------------------------


def _csv(text: str):  # noqa: ANN202
    return io.StringIO(text)


def test_an_import_creates_keywords_and_records_positions(admin, tenant):
    org, _user = tenant

    result = import_keyword_positions(
        organization=org, actor=admin,
        file_obj=_csv("Keyword,Position,Date\nsofas,4,2026-03-01\n"
                      "armchairs,11,2026-03-01\n"),
    )

    assert result.keywords_created == 2
    assert result.positions_recorded == 2
    assert Keyword.objects.filter(organization=org).count() == 2


def test_an_import_understands_the_usual_column_names(admin, tenant):
    """Different rank trackers spell the same column differently."""
    org, _user = tenant

    result = import_keyword_positions(
        organization=org, actor=admin,
        file_obj=_csv("Query,Rank\nsofas,4\n"),
    )

    assert result.positions_recorded == 1


def test_an_import_copes_with_a_byte_order_mark(admin, tenant):
    """Spreadsheet exports routinely carry one, and it would otherwise
    become part of the first column's name."""
    org, _user = tenant
    raw = "﻿keyword,position\nsofas,4\n".encode()

    result = import_keyword_positions(organization=org, actor=admin,
                                      file_obj=io.BytesIO(raw))

    assert result.positions_recorded == 1


def test_an_import_refuses_a_position_it_cannot_read(admin, tenant):
    """A wrong rank silently stored is worse than a row rejected."""
    org, _user = tenant

    result = import_keyword_positions(
        organization=org, actor=admin,
        file_obj=_csv("keyword,position\nsofas,four\n"),
    )

    assert result.positions_recorded == 0
    assert result.rows_skipped == 1
    assert "not a position" in result.problems[0]


def test_an_import_treats_not_ranked_as_a_real_observation(admin, tenant):
    """Different from a parse failure: somebody looked and it was not
    there."""
    org, _user = tenant

    result = import_keyword_positions(
        organization=org, actor=admin,
        file_obj=_csv("keyword,position\nsofas,-\n"),
    )

    assert result.positions_recorded == 1
    assert KeywordRanking.objects.get().position is None


def test_an_import_rejects_a_file_with_no_keyword_column(admin, tenant):
    org, _user = tenant

    result = import_keyword_positions(
        organization=org, actor=admin,
        file_obj=_csv("something,else\n1,2\n"),
    )

    assert not result.did_anything
    assert "No keyword column" in result.problems[0]


def test_an_import_does_not_overwrite_a_priority_set_by_hand(admin, tenant):
    """An import updates positions, never a decision somebody made."""
    org, _user = tenant
    keyword = make_keyword(org, actor=admin, term="sofas", priority=1)

    import_keyword_positions(
        organization=org, actor=admin,
        file_obj=_csv("keyword,position\nsofas,4\n"),
    )

    keyword.refresh_from_db()
    assert keyword.priority == 1


def test_re_importing_the_same_day_replaces_rather_than_duplicates(admin, tenant):
    org, _user = tenant
    csv_text = "keyword,position,date\nsofas,9,2026-03-01\n"

    import_keyword_positions(organization=org, actor=admin,
                             file_obj=_csv(csv_text))
    import_keyword_positions(
        organization=org, actor=admin,
        file_obj=_csv("keyword,position,date\nsofas,4,2026-03-01\n"),
    )

    assert KeywordRanking.objects.count() == 1
    assert KeywordRanking.objects.get().position == 4


def test_every_imported_reading_records_where_it_came_from(admin, tenant):
    """So a figure can always be traced back."""
    org, _user = tenant

    import_keyword_positions(organization=org, actor=admin,
                             file_obj=_csv("keyword,position\nsofas,4\n"),
                             source="Ahrefs export")

    assert KeywordRanking.objects.get().source == "Ahrefs export"


# ---------------------------------------------------------------------------
# Through the staff pages
# ---------------------------------------------------------------------------


def test_the_workspace_shows_an_empty_state_before_anything_is_recorded(
    client, admin, tenant
):
    org, _user = tenant
    sign_in(client, admin)

    body = client.get(reverse("staff:seo_workspace", args=[org.slug])).content

    assert b"Nothing recorded for this site yet" in body


def test_the_workspace_shows_the_summary_once_there_is_data(client, admin,
                                                            tenant):
    org, _user = tenant
    keyword = make_keyword(org, actor=admin, term="interior designer")
    make_position(keyword, position=4)
    sign_in(client, admin)

    body = client.get(reverse("staff:seo_workspace", args=[org.slug])).content

    assert b"Keywords tracked" in body
    assert b"interior designer" in body


def test_staff_can_add_a_keyword_through_the_form(client, admin, tenant):
    org, _user = tenant
    sign_in(client, admin)

    response = client.post(
        reverse("staff:seo_keyword_create", args=[org.slug]),
        {"term": "velvet sofa", "priority": "2"},
    )

    assert response.status_code == 302
    assert Keyword.objects.filter(organization=org, term="velvet sofa").exists()


def test_staff_can_import_a_csv_through_the_form(client, admin, tenant):
    from django.core.files.uploadedfile import SimpleUploadedFile

    org, _user = tenant
    sign_in(client, admin)
    upload = SimpleUploadedFile(
        "ranks.csv", b"keyword,position\nvelvet sofa,6\n", content_type="text/csv",
    )

    response = client.post(
        reverse("staff:seo_keyword_import", args=[org.slug]),
        {"file": upload, "source": "Test export"},
    )

    assert response.status_code == 302
    assert Keyword.objects.filter(organization=org, term="velvet sofa").exists()


def test_the_import_form_refuses_a_file_that_is_not_a_csv(client, admin, tenant):
    from django.core.files.uploadedfile import SimpleUploadedFile

    org, _user = tenant
    sign_in(client, admin)
    upload = SimpleUploadedFile("ranks.xlsx", b"not a csv",
                                content_type="application/vnd.ms-excel")

    client.post(reverse("staff:seo_keyword_import", args=[org.slug]),
                {"file": upload})

    assert not Keyword.objects.filter(organization=org).exists()


def test_a_reader_cannot_create_records(client, tenant):
    org, _user = tenant
    reader = make_staff_member(
        "reader@heliograph.agency",
        roles=[make_role("Reader", ["seo_view", "organizations_view"])],
    )
    from apps.staff.tests.factories import assign_client

    assign_client(reader, org)
    sign_in(client, reader.user)

    response = client.post(
        reverse("staff:seo_keyword_create", args=[org.slug]),
        {"term": "sneaky", "priority": "2"},
    )

    assert response.status_code == 403
    assert not Keyword.objects.filter(term="sneaky").exists()


# ---------------------------------------------------------------------------
# The client's own view
# ---------------------------------------------------------------------------


def _give_seo_service(organization, admin):  # noqa: ANN001
    from apps.subscriptions.models import SubscriptionStatus
    from apps.subscriptions.tests.factories import make_service, make_subscription

    return make_subscription(
        organization, actor=admin,
        service=make_service("SEO retainer", category_slug="search",
                             workspace_module="seo"),
        status=SubscriptionStatus.ACTIVE,
    )


def test_a_client_sees_their_keywords_and_figures(client, admin, tenant):
    org, user = tenant
    _give_seo_service(org, admin)
    keyword = make_keyword(org, actor=admin, term="interior designer")
    make_position(keyword, position=4)
    sign_in(client, user)

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"interior designer" in body
    assert b"Keywords tracked" in body


def test_the_client_page_says_where_the_numbers_come_from(client, admin, tenant):
    """No invented live data, and the page says so."""
    org, user = tenant
    _give_seo_service(org, admin)
    make_position(make_keyword(org, actor=admin), position=4)
    sign_in(client, user)

    text = client.get(
        reverse("organizations:portal_module", args=["seo"])).content.decode()

    assert "not from a live search" in " ".join(text.split())


def test_a_client_with_the_service_but_no_data_is_told_so(client, admin, tenant):
    org, user = tenant
    _give_seo_service(org, admin)
    sign_in(client, user)

    body = client.get(
        reverse("organizations:portal_module", args=["seo"])).content

    assert b"until it is real" in b" ".join(body.split())
