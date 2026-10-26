"""Template hygiene.

Caught in review when a rendered page showed its own source comment: a
`{# … #}` that spans lines is not a comment to Django's parser, so it is
emitted verbatim to the visitor. It renders fine in an editor, which is
what makes it easy to miss.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

TEMPLATE_DIR = Path(settings.BASE_DIR) / "templates"
TEMPLATES = sorted(TEMPLATE_DIR.rglob("*.html"))


def test_templates_were_found():
    assert TEMPLATES, "no templates discovered — has the directory moved?"


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: str(p.name))
def test_no_comment_spans_more_than_one_line(path):
    """Django's `{# … #}` is single-line. Use `{% comment %}` for prose."""
    offenders = [
        number
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if "{#" in line and "#}" not in line
    ]

    assert not offenders, (
        f"{path.relative_to(TEMPLATE_DIR)} lines {offenders}: a multi-line "
        "{# … #} is rendered to the page. Use {% comment %} … {% endcomment %}."
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [reverse("public:home"), reverse("accounts:login"), "/this-page-does-not-exist/"],
)
def test_rendered_pages_leak_no_template_syntax(url, settings):
    """The end of the same bug: whatever the cause, raw template syntax
    must never reach the browser."""
    settings.DEBUG = False
    content = Client().get(url).content

    for marker in (b"{#", b"#}", b"{%", b"%}", b"{{"):
        assert marker not in content, f"{url} leaked {marker!r}"


@pytest.mark.django_db
def test_the_styleguide_leaks_no_template_syntax(client, settings):
    settings.DEBUG = True
    content = client.get(reverse("core:styleguide")).content

    for marker in (b"{#", b"#}", b"{%", b"%}", b"{{"):
        assert marker not in content, f"styleguide leaked {marker!r}"


def test_the_standalone_error_page_depends_on_no_context_processor():
    """500.html renders with an empty context, and may be rendering
    because the database or the static manifest is the thing that broke.
    It must not reference either."""
    source = (TEMPLATE_DIR / "errors" / "500.html").read_text()

    assert "{% extends" not in source
    assert "{% static" not in source
    assert "{{ site_name }}" not in source
