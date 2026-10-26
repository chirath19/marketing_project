"""Business components.

They take whatever object a caller has — a model instance, a dataclass, a
dict — and read attributes off it, so they can be built and reviewed
before the domain models exist. These tests pin that contract down.
"""

import pytest
from django.template import Context, Template

from apps.core import styleguide_data


def render(template_string: str, **context) -> str:
    return Template("{% load ui %}" + template_string).render(Context(context))


# --- service card ----------------------------------------------------------


def test_a_service_card_shows_price_period_and_inclusions():
    service = styleguide_data.SERVICES[0]
    html = render("{% ui_service_card s href='/x/' %}", s=service)

    assert service.name in html
    assert service.price_display in html
    assert service.billing_period in html
    assert "What is included" in html
    assert "Monthly content plan" in html


def test_service_inclusions_use_details_so_they_work_without_javascript():
    html = render("{% ui_service_card s %}", s=styleguide_data.SERVICES[0])

    assert "<details" in html
    assert "<summary" in html


def test_the_add_to_quote_button_names_the_service_it_adds():
    """A page of twelve identical "Add to quote" buttons is unusable with
    a screen reader."""
    service = styleguide_data.SERVICES[0]
    html = render("{% ui_service_card s %}", s=service)

    assert f"sr-only\">: {service.name}" in html


def test_a_service_card_renders_from_a_plain_dict():
    html = render(
        "{% ui_service_card s %}",
        s={"name": "Ad hoc consulting", "category": "Advisory",
           "summary": "By the hour.", "price_display": "$180",
           "billing_period": "per hour", "inclusions": []},
    )

    assert "Ad hoc consulting" in html
    assert "$180" in html


def test_a_service_card_tolerates_missing_optional_fields():
    """A half-populated record should still produce a usable card."""
    html = render("{% ui_service_card s %}", s={"name": "Bare", "price_display": "$1"})

    assert "Bare" in html
    assert "What is included" not in html


# --- campaign / client / lead ---------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected_class"),
    [("live", "text-live"), ("paused", "text-paused"),
     ("planned", "text-planned"), ("done", "text-done")],
)
def test_a_campaign_card_colours_its_status_from_the_shared_map(status, expected_class):
    html = render(
        "{% ui_campaign_card c %}",
        c={"name": "Brand search", "module_label": "Paid ads", "status": status,
           "spend_display": "$6,100", "result_summary": "5.6x ROAS"},
    )

    assert expected_class in html


def test_a_campaign_card_shows_the_result_summary_from_the_reference():
    html = render("{% ui_campaign_card c %}", c=styleguide_data.CAMPAIGNS[1])

    assert "61 links won" in html


def test_a_client_card_shows_its_account_manager():
    html = render("{% ui_client_card c %}", c=styleguide_data.CLIENTS[0])

    assert "Amara Silva" in html
    assert "Northwind Supply" in html


def test_a_lead_card_links_the_email_as_a_contact_detail():
    html = render("{% ui_lead_card l %}", l=styleguide_data.LEADS[0])

    assert "mailto:priya@vantage.example" in html


# --- approvals -------------------------------------------------------------


def test_approve_and_reject_are_form_submissions_not_links():
    """A decision changes state, so it must not be triggered by a browser
    prefetch or a crawler following a link."""
    html = render(
        "{% ui_approval_card a approve_url='/approve/1/' reject_url='/reject/1/' %}",
        a=styleguide_data.APPROVALS[0],
    )

    assert '<form method="post" action="/approve/1/"' in html
    assert '<form method="post" action="/reject/1/"' in html
    assert 'href="/approve/1/"' not in html


def test_each_approval_button_names_the_item_it_decides():
    approval = styleguide_data.APPROVALS[0]
    html = render("{% ui_approval_card a approve_url='/a/' %}", a=approval)

    assert f"sr-only\">: {approval.title}" in html


def test_a_reject_button_is_absent_when_no_reject_url_is_given():
    html = render("{% ui_approval_card a approve_url='/a/' %}",
                  a=styleguide_data.APPROVALS[0])

    assert "Reject" not in html


# --- timeline, notifications, inbox ---------------------------------------


def test_the_activity_timeline_is_an_ordered_list():
    """The sequence is the meaning."""
    html = render("{% ui_activity_timeline entries %}", entries=styleguide_data.ACTIVITY)

    assert "<ol" in html
    assert "61st backlink won" in html


def test_an_empty_timeline_falls_back_to_an_empty_state():
    html = render("{% ui_activity_timeline entries empty_title='No activity yet' %}",
                  entries=[])

    assert "No activity yet" in html
    assert "<ol" not in html


def test_a_read_notification_is_not_announced_as_unread():
    html = render(
        "{% ui_notification_item n %}",
        n={"title": "April report is ready", "body": "", "created_at": "yesterday",
           "is_read": True},
    )

    assert "Unread." not in html


def test_an_inbox_item_marks_the_open_conversation_as_current():
    html = render("{% ui_inbox_message_item m href='/m/1/' selected=True %}",
                  m=styleguide_data.INBOX[0])

    assert 'aria-current="true"' in html


def test_an_inbox_item_shows_what_kind_of_message_it_is():
    html = render("{% ui_inbox_message_item m %}", m=styleguide_data.INBOX[0])

    assert "Quote request" in html


# --- escaping --------------------------------------------------------------


def test_business_components_escape_record_content():
    """Records come from client-submitted forms."""
    html = render(
        "{% ui_lead_card l %}",
        l={"name": "<script>alert(1)</script>", "company": "", "email": "",
           "source": "", "status": "pending", "summary": "", "value_display": "",
           "created_at": ""},
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_an_approval_summary_reads_as_a_sentence_not_a_spaced_list():
    """Template newlines render as spaces; "Paid ads , $2,900" is what
    that looks like on the page."""
    html = render(
        "{% ui_approval_card a %}",
        a={"title": "Spring video test", "module_label": "Paid ads",
           "summary": "$2,900 budget", "status": "pending"},
    )

    assert "Paid ads, $2,900 budget" in html
    assert "Paid ads ," not in html


def test_an_approval_with_only_a_module_label_has_no_dangling_comma():
    html = render(
        "{% ui_approval_card a %}",
        a={"title": "T", "module_label": "Email", "summary": "", "status": "pending"},
    )

    assert "Email," not in html
