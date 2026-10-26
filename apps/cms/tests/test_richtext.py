"""The content formatter.

Its whole job is to turn author text into a fixed set of elements without
ever letting the author produce markup of their own. These tests are the
guard on that.
"""

import pytest

from apps.cms.richtext import plain_text, reading_minutes, render

# --- safety ------------------------------------------------------------------


def test_html_in_the_source_is_escaped_not_rendered():
    """Escape first, then format. Anything typed is text, not markup."""
    html = render("<script>alert(1)</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_an_img_tag_cannot_be_smuggled_in():
    html = render('<img src=x onerror="alert(1)">')

    assert "onerror" not in html or "&lt;img" in html
    assert "<img" not in html


@pytest.mark.parametrize("scheme", [
    "javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
])
def test_an_unsafe_link_scheme_is_dropped(scheme):
    """The one place markup is produced is a link, so the scheme is
    checked there. The author's words survive; the destination does not."""
    html = render(f"[click me]({scheme})")

    assert "click me" in html
    assert "javascript:" not in html
    assert "data:text/html" not in html
    assert "vbscript:" not in html
    assert "<a href" not in html


@pytest.mark.parametrize("url", [
    "https://example.com", "http://example.com", "mailto:a@example.com",
    "tel:+94112345678", "/services/", "#section",
])
def test_a_safe_link_scheme_is_kept(url):
    html = render(f"[label]({url})")

    assert f'href="{url}"' in html


def test_an_external_link_opens_safely():
    """`rel="noopener"` so the opened page cannot reach back through
    window.opener."""
    html = render("[example](https://example.com)")

    assert 'target="_blank"' in html
    assert 'rel="noopener"' in html


def test_an_internal_link_stays_in_the_tab():
    html = render("[services](/services/)")

    assert 'target="_blank"' not in html


# --- formatting --------------------------------------------------------------


def test_blank_lines_separate_paragraphs():
    html = render("First para.\n\nSecond para.")

    assert html.count("<p") == 2


def test_headings_are_produced():
    html = render("## Big\n\n### Smaller")

    assert "<h2" in html
    assert "<h3" in html
    assert "Big" in html


def test_an_unordered_list_is_produced():
    html = render("- one\n- two\n- three")

    assert "<ul" in html
    assert html.count("<li>") == 3


def test_an_ordered_list_is_produced():
    html = render("1. first\n2. second")

    assert "<ol" in html
    assert html.count("<li>") == 2


def test_two_adjacent_lists_of_different_kinds_do_not_merge():
    html = render("- bullet\n\n1. number")

    assert "<ul" in html
    assert "<ol" in html


def test_a_list_is_closed_before_the_next_paragraph():
    html = render("- one\n\nAfter the list.")

    assert html.index("</ul>") < html.index("After the list.")


def test_a_quote_is_produced():
    html = render("> Something quotable.")

    assert "<blockquote" in html
    assert "Something quotable." in html


def test_bold_and_italic():
    html = render("This is **bold** and this is *italic*.")

    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html


def test_bold_is_not_mistaken_for_italic():
    html = render("**both**")

    assert "<strong>both</strong>" in html
    assert "<em>" not in html


def test_empty_content_renders_nothing():
    assert render("") == ""
    assert render(None) == ""


def test_windows_line_endings_are_handled():
    html = render("One.\r\n\r\nTwo.")

    assert html.count("<p") == 2


# --- derived values ----------------------------------------------------------


def test_plain_text_strips_the_formatting_markers():
    text = plain_text("## Heading\n\n- item\n\n[link](https://x.com) **bold**")

    assert "#" not in text
    assert "**" not in text
    assert "https://x.com" not in text
    assert "link" in text


def test_reading_time_is_never_zero():
    """"0 min read" reads like a bug rather than a short post."""
    assert reading_minutes("Three short words.") == 1
    assert reading_minutes("") == 1


def test_reading_time_scales_with_length():
    assert reading_minutes(" ".join(["word"] * 600)) == 3


# ---------------------------------------------------------------------------
# Wrapped source is still one paragraph
# ---------------------------------------------------------------------------


def test_wrapped_lines_become_one_paragraph():
    """An author who wraps at seventy columns means one paragraph.

    Before this, every source line became its own `<p>`, so a normally
    wrapped article rendered as a column of disconnected fragments.
    """
    html = render("The first line of a thought\nand the rest of it.")

    assert html.count("<p") == 1
    assert "The first line of a thought and the rest of it." in html


def test_formatting_survives_a_line_break():
    """`**bold**` that opens on one line and closes on the next.

    The two halves have to be in the same string for the pattern to
    match, which is only true once wrapped lines are joined.
    """
    html = render("What you need is **cost per\ncustomer**, not clicks.")

    assert "<strong>cost per customer</strong>" in html
    assert "**" not in html


def test_a_blank_line_still_starts_a_new_paragraph():
    html = render("First paragraph.\n\nSecond paragraph.")

    assert html.count("<p") == 2


def test_a_heading_ends_the_paragraph_before_it():
    html = render("Some prose.\n## A heading\nMore prose.")

    assert html.index("Some prose.") < html.index("<h2")
    assert html.index("<h2") < html.index("More prose.")


def test_a_list_ends_the_paragraph_before_it():
    html = render("Lead-in line.\n- first\n- second")

    assert html.index("Lead-in line.") < html.index("<ul")
    assert html.count("<li>") == 2
