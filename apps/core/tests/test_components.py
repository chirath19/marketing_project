"""The design system's behaviour, not its appearance."""

import pytest
from django.template import Context, Template


def render(template_string: str, **context) -> str:
    return Template("{% load ui %}" + template_string).render(Context(context))


def test_button_renders_an_anchor_when_given_an_href():
    """A navigation control must be a link, so it can be opened in a new
    tab and announced as a link by a screen reader."""
    html = render('{% ui_button label="Browse" href="/catalog/" %}')

    assert "<a href=\"/catalog/\"" in html
    assert "Browse" in html


def test_button_renders_a_button_without_an_href():
    html = render('{% ui_button label="Approve" type="submit" %}')

    assert "<button type=\"submit\"" in html


def test_disabled_button_is_disabled_in_markup():
    html = render('{% ui_button label="Approve" disabled=True %}')

    assert "disabled" in html


@pytest.mark.parametrize(
    ("tone", "expected"),
    [("live", "text-live"), ("paused", "text-paused"),
     ("planned", "text-planned"), ("done", "text-done")],
)
def test_badge_tones_map_to_brand_classes(tone, expected):
    html = render(f'{{% ui_badge label="x" tone="{tone}" %}}')

    assert expected in html


def test_unknown_badge_tone_falls_back_rather_than_rendering_unstyled():
    html = render('{% ui_badge label="x" tone="chartreuse" %}')

    assert "bg-mist" in html


def test_progress_bar_computes_a_percentage():
    html = render("{% ui_progress current=412 target=450 label='SEO' %}")

    assert "412 of 450" in html
    assert "width: 91.6%" in html


def test_progress_bar_clamps_above_target():
    """Exceeding a goal is good news, not a bar overflowing its track."""
    html = render("{% ui_progress current=500 target=450 %}")

    assert "width: 100.0%" in html


def test_progress_bar_survives_a_zero_target():
    html = render("{% ui_progress current=10 target=0 %}")

    assert "width: 0.0%" in html


def test_progress_bar_is_announced_to_assistive_technology():
    html = render("{% ui_progress current=50 target=100 label='SEO' %}")

    assert 'role="progressbar"' in html
    assert 'aria-valuenow="50.0"' in html


def test_metric_card_tone_is_caller_chosen_not_inferred():
    """A falling cost per lead is good; falling revenue is not. The
    component must not guess which."""
    good = render('{% ui_metric_card label="CPL" value="$21.70" delta="8%" direction="good" %}')
    bad = render('{% ui_metric_card label="Revenue" value="$10" delta="8%" direction="bad" %}')

    assert "text-live" in good
    assert "text-danger" in bad


def test_django_messages_error_tag_maps_to_the_danger_tone():
    """Django emits `error`; the alert palette must not silently drop it."""
    html = render('{% ui_alert message="Nope" tone="error" %}')

    assert "text-danger" in html


def test_card_component_wraps_its_slot():
    html = render(
        '{% component "card" title="Recent activity" %}<p>Inside</p>{% endcomponent %}'
    )

    assert "Recent activity" in html
    assert "<p>Inside</p>" in html


def test_component_tag_requires_a_name():
    from django.template import TemplateSyntaxError

    with pytest.raises(TemplateSyntaxError, match="requires a component name"):
        render("{% component %}{% endcomponent %}")


def test_component_tag_rejects_positional_arguments():
    from django.template import TemplateSyntaxError

    with pytest.raises(TemplateSyntaxError, match="keyword arguments"):
        render('{% component "card" "Recent" %}{% endcomponent %}')


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def _page(number: int, num_pages: int):
    from apps.core.styleguide_data import Page, Paginator

    return Page(number=number, paginator=Paginator(num_pages=num_pages, count=num_pages * 25),
                start_index_value=1, end_index_value=25)


def test_pagination_is_absent_when_there_is_only_one_page():
    """A pager for a single page is noise and an extra tab stop."""
    html = render("{% ui_pagination page %}", page=_page(1, 1))

    assert html.strip() == ""


def test_pagination_marks_the_current_page():
    html = render("{% ui_pagination page %}", page=_page(4, 12))

    assert 'aria-current="page"' in html


def test_pagination_windows_long_ranges_with_an_ellipsis():
    """Twelve pages is fine; three hundred would be a wall of links."""
    html = render("{% ui_pagination page %}", page=_page(50, 300))

    assert "&hellip;" in html
    assert ">1</a>" in html
    assert ">300</a>" in html


def test_pagination_does_not_offer_a_previous_link_on_the_first_page():
    html = render("{% ui_pagination page %}", page=_page(1, 12))

    assert "?page=0" not in html


def test_pagination_preserves_the_existing_querystring():
    """Otherwise paging silently drops the filter the user applied.

    The ampersand is escaped to `&amp;` in the href, which is the correct
    encoding inside an HTML attribute.
    """
    html = render("{% ui_pagination page querystring='status=live' %}", page=_page(2, 12))

    assert "?status=live&amp;page=3" in html
    assert "?status=live&amp;page=1" in html


def test_pagination_handles_a_missing_page_object():
    assert render("{% ui_pagination page %}", page=None).strip() == ""


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------


def test_component_labels_are_escaped():
    html = render("{% ui_badge label=value %}", value="<script>alert(1)</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_passed_through_attributes_are_escaped():
    html = render('{% ui_button label="Go" data_test=value %}', value='" onclick="evil()')

    assert 'onclick="evil()' not in html


def test_extra_classes_are_merged_rather_than_duplicated():
    """Emitting a second `class` attribute produces markup where the
    browser keeps the first and silently drops the caller's — a
    responsive utility passed that way simply never applied."""
    html = render('{% ui_button label="Go" extra_class="sm:hidden" %}')

    assert html.count("class=") == 1
    assert "sm:hidden" in html
    assert "bg-gold" in html, "the component's own classes survive"


def test_a_class_keyword_is_merged_too_not_emitted_twice():
    html = render('{% ui_icon_button icon="x" label="Close" class="lg:hidden" %}')

    assert html.count("class=") == 2, "one on the control, one on the sr-only span"
    assert "lg:hidden" in html
