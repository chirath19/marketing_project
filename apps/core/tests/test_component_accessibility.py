"""Accessibility contracts for the component library.

These assert the things that are invisible when they break: an icon
button with no name, a dialog that does not announce itself, a state
conveyed only by colour. Every one of them is a bug a sighted mouse user
would never notice.
"""

import pytest
from django.template import Context, Template

from apps.core.forms import StyleguideDemoForm


def render(template_string: str, **context) -> str:
    return Template("{% load ui %}" + template_string).render(Context(context))


# --- naming ----------------------------------------------------------------


def test_an_icon_button_has_an_accessible_name():
    """The glyph is hidden; the name comes from visually-hidden text."""
    html = render('{% ui_icon_button icon="&times;" label="Remove filter" %}')

    assert 'aria-hidden="true"' in html
    assert '<span class="sr-only">Remove filter</span>' in html


def test_a_search_box_has_a_real_label_not_just_a_placeholder():
    """A placeholder disappears the moment someone types."""
    html = render('{% ui_search_box name="q" placeholder="Search campaigns" %}')

    assert 'class="sr-only"' in html
    assert 'for="id_q"' in html
    assert 'type="search"' in html


def test_a_table_names_itself_and_scopes_its_headers(table_columns):
    html = render(
        '{% component "table" caption="Campaigns" columns=columns %}'
        '<tr><td class="ui-td" data-label="Campaign">Brand search</td></tr>'
        "{% endcomponent %}",
        columns=table_columns,
    )

    assert "<caption" in html
    assert "Campaigns" in html
    assert 'scope="col"' in html
    assert 'data-label="Campaign"' in html


@pytest.fixture
def table_columns():
    return [{"label": "Campaign"}, {"label": "Spend", "align": "right"}]


# --- current state ---------------------------------------------------------


def test_the_active_tab_is_marked_current_not_only_coloured():
    html = render(
        "{% ui_tabs tabs active='live' %}",
        tabs=[{"key": "all", "label": "All", "href": "?a"},
              {"key": "live", "label": "Live", "href": "?l"}],
    )

    assert 'aria-current="page"' in html
    assert html.count('aria-current="page"') == 1


def test_the_current_breadcrumb_is_text_rather_than_a_link():
    """A link to the page you are on is a tab stop that goes nowhere."""
    html = render(
        "{% ui_breadcrumbs items current='Brand search' %}",
        items=[{"label": "Dashboard", "href": "/"}],
    )

    assert 'aria-current="page"' in html
    assert 'href="/"' in html
    assert "<a" not in html.split("aria-current")[1]


def test_an_active_nav_item_is_marked_current():
    html = render('{% ui_nav_item label="Overview" href="/" active=True %}')

    assert 'aria-current="page"' in html


def test_an_unread_notification_says_so_in_words(notification):
    """Unread is shown with a gold dot. Colour alone is not a state."""
    html = render("{% ui_notification_item n %}", n=notification)

    assert "Unread." in html


@pytest.fixture
def notification():
    class N:
        title = "Approval needed"
        body = "Paid ads"
        created_at = "10 minutes ago"
        is_read = False
        severity = "pending"
        link = ""
    return N()


# --- dialogs ---------------------------------------------------------------


def test_a_modal_announces_itself_as_a_dialog_and_names_itself():
    html = render(
        '{% component "modal" id="sg" title="Add a service" %}body{% endcomponent %}'
    )

    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-labelledby="sg-title"' in html
    assert 'id="sg-title"' in html


def test_a_modal_description_slot_is_wired_to_aria_describedby():
    html = render(
        '{% component "modal" id="sg" title="T" %}'
        '{% slot "description" %}Why this matters{% endslot %}'
        "{% endcomponent %}"
    )

    assert 'aria-describedby="sg-description"' in html
    assert 'id="sg-description"' in html


def test_a_modal_without_a_description_does_not_point_at_a_missing_id():
    """A dangling aria-describedby is worse than none at all."""
    html = render('{% component "modal" id="sg" title="T" %}body{% endcomponent %}')

    assert "aria-describedby" not in html


def test_a_confirmation_uses_alertdialog():
    html = render(
        '{% component "confirm_dialog" id="c" title="Archive?" message="Sure?" action="/go/" %}'
        "{% endcomponent %}"
    )

    assert 'role="alertdialog"' in html
    assert 'aria-describedby="c-message"' in html


def test_a_confirmation_submits_a_form_rather_than_following_a_link():
    """Confirming changes state, so it must not be reachable by a
    prefetch or a crawler."""
    html = render(
        '{% component "confirm_dialog" id="c" title="Archive?" message="Sure?" '
        'action="/campaigns/1/archive/" confirm_label="Archive" destructive=True %}'
        "{% endcomponent %}",
    )

    assert '<form method="post" action="/campaigns/1/archive/"' in html
    assert 'type="submit"' in html
    assert "bg-danger" in html


def test_a_dropdown_reports_its_expanded_state():
    html = render('{% component "dropdown" label="Actions" %}items{% endcomponent %}')

    assert 'aria-haspopup="true"' in html
    assert ":aria-expanded=" in html
    assert 'role="menu"' in html


# --- forms -----------------------------------------------------------------


def test_a_bound_field_with_an_error_is_marked_invalid_and_described():
    form = StyleguideDemoForm(data={"full_name": "", "work_email": "nope"})
    assert not form.is_valid()

    html = render("{% ui_field field %}", field=form["work_email"])

    assert 'aria-invalid="true"' in html
    assert 'aria-describedby="id_work_email_error"' in html
    assert 'id="id_work_email_error"' in html


def test_help_text_is_linked_to_its_control():
    form = StyleguideDemoForm()
    html = render("{% ui_field field %}", field=form["website"])

    assert 'aria-describedby="id_website_help"' in html
    assert 'id="id_website_help"' in html


def test_a_radio_group_is_wrapped_in_a_fieldset_with_a_legend():
    """Without them each radio is announced alone, with no indication of
    what the choice is for."""
    form = StyleguideDemoForm()
    html = render("{% ui_field field %}", field=form["channel"])

    assert "<fieldset" in html
    assert "<legend" in html


def test_a_checkbox_label_follows_its_control():
    form = StyleguideDemoForm()
    html = render("{% ui_field field %}", field=form["consent"])

    assert html.index("<input") < html.index("<label")


def test_a_required_field_is_marked_required_in_markup():
    form = StyleguideDemoForm()
    html = render("{% ui_field field %}", field=form["full_name"])

    assert "required" in html


def test_the_error_summary_links_to_the_field_that_failed():
    """So a keyboard user can jump straight to the input, not hunt for it."""
    form = StyleguideDemoForm(data={"full_name": "", "work_email": "nope"})
    assert not form.is_valid()

    html = render("{% ui_form_errors form %}", form=form)

    assert 'href="#id_work_email"' in html
    assert 'role="alert"' in html


def test_the_error_summary_is_absent_when_the_form_is_clean():
    html = render("{% ui_form_errors form %}", form=StyleguideDemoForm())

    assert html.strip() == ""


def test_a_file_upload_is_a_real_input_wrapped_by_its_label():
    """Drag and drop is an enhancement, never the only way in."""
    html = render('{% ui_file_upload name="creative" label="Upload a creative" %}')

    assert 'type="file"' in html
    assert 'for="id_creative"' in html
    assert 'id="id_creative"' in html


# --- loading ---------------------------------------------------------------


def test_a_skeleton_is_hidden_from_assistive_technology():
    """A screen reader should hear "Loading" once, not read a wall of
    empty boxes."""
    html = render("{% ui_skeleton lines=4 %}")

    assert 'aria-hidden="true"' in html
    assert 'role="status"' in html
    assert "Loading" in html


def test_a_progress_bar_reports_its_value():
    html = render("{% ui_progress current=412 target=450 label='SEO' %}")

    assert 'role="progressbar"' in html
    assert 'aria-valuenow="91.6"' in html
    assert 'aria-valuemax="100"' in html


# --- the mixin must not validate early -------------------------------------


def test_the_styled_mixin_does_not_validate_during_init():
    """Reading `self.errors` in `__init__` runs full_clean() before a
    subclass has finished configuring its fields, so a later
    `required = True` is silently ignored and the cached errors are never
    recomputed. That shipped once; this is the guard."""
    from django import forms

    from apps.core.forms import StyledForm

    class LateConfiguredForm(StyledForm):
        optional_on_paper = forms.CharField(required=False)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields["optional_on_paper"].required = True

    form = LateConfiguredForm(data={"optional_on_paper": ""})

    assert not form.is_valid()
    assert "optional_on_paper" in form.errors


def test_a_form_is_not_cleaned_merely_by_being_constructed():
    from django import forms

    from apps.core.forms import StyledForm

    class CountingForm(StyledForm):
        name = forms.CharField()
        cleaned_times = 0

        def clean(self):
            type(self).cleaned_times += 1
            return super().clean()

    form = CountingForm(data={"name": "x"})
    assert CountingForm.cleaned_times == 0, "constructing the form validated it"

    form.is_valid()
    assert CountingForm.cleaned_times == 1


def test_a_dropdown_label_cannot_push_its_chevron_off_screen():
    """A long email in the account menu overflowed the top bar at phone
    width, taking the disclosure arrow with it."""
    html = render('{% component "dropdown" label="verylong@example.agency" %}x{% endcomponent %}')

    assert "truncate" in html
    assert "shrink-0" in html
