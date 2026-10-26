"""Components must not leak the page's context onto the page.

A component template is rendered with `render_to_string(..., request=…)`,
so the context processors run for it too. That means a component
argument sharing a name with a global context variable — `brand`, say —
renders that variable whenever the caller omits the argument. It happened:
the sidebar printed the entire brand dict onto the page.

These tests render every container component with no arguments at all and
assert nothing reprs itself into the output.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template
from django.test import RequestFactory

COMPONENT_DIR = Path(settings.BASE_DIR) / "templates" / "components"

# Components whose whole purpose is to render a passed-in record; rendering
# them with nothing is meaningless rather than informative.
RECORD_COMPONENTS = {"image.html"}

CONTAINERS = sorted(
    p for p in COMPONENT_DIR.glob("*.html")
    if p.name not in RECORD_COMPONENTS
)

# Anything that looks like a Python repr rather than rendered content.
REPR_MARKERS = ["{'", "': '", "<django.", "object at 0x", "QuerySet [",
                "dict_keys", "SafeString("]


@pytest.mark.django_db
@pytest.mark.parametrize("path", CONTAINERS, ids=lambda p: p.name)
def test_a_component_rendered_with_no_arguments_leaks_nothing(path, client):
    """The context processors still run for a component's own render."""
    request = RequestFactory().get("/")
    request.user = None

    template = Template(
        '{% load ui %}{% component "' + path.stem + '" %}body{% endcomponent %}'
    )
    html = template.render(Context({"request": request}, autoescape=True))

    for marker in REPR_MARKERS:
        assert marker not in html, f"{path.name} leaked a repr containing {marker!r}"


@pytest.mark.django_db
def test_the_sidebar_does_not_print_the_brand_context():
    """The specific regression: `{% if brand %}` matched the global
    context variable and rendered the dict."""
    request = RequestFactory().get("/")

    html = Template(
        '{% load ui %}{% component "sidebar" %}links{% endcomponent %}'
    ).render(Context({"request": request}))

    assert "theme_color" not in html
    assert "Heliograph" not in html
    assert "links" in html


@pytest.mark.django_db
def test_a_component_still_renders_an_argument_the_caller_passes():
    request = RequestFactory().get("/")

    html = Template(
        '{% load ui %}{% component "sidebar" heading="Staff" %}links{% endcomponent %}'
    ).render(Context({"request": request}))

    assert "Staff" in html


@pytest.mark.django_db
def test_no_page_template_renders_the_brand_dict_itself(client, settings):
    """`{{ brand }}` on a page would print the dict. It is `brand.name`."""
    settings.DEBUG = True
    for url in ("/", "/styleguide/", "/accounts/login/"):
        content = client.get(url).content.decode()
        assert "theme_color" not in content, url
        assert "'contact_email'" not in content, url


@pytest.mark.django_db
def test_a_table_column_with_a_blank_label_leaks_no_repr():
    """`{{ column.label|default:column }}` fires `default` on an empty
    label and prints the mapping's repr as the heading. It shipped that
    way, and showed `{'LABEL': '', 'ALIGN': 'RIGHT'}` on the page."""
    request = RequestFactory().get("/")

    html = Template(
        '{% load ui %}{% component "table" columns=columns %}'
        '<tr><td class="ui-td">x</td></tr>{% endcomponent %}'
    ).render(Context({
        "request": request,
        "columns": [{"label": "Name"}, {"label": "", "align": "right"}],
    }))

    assert "{'" not in html
    assert "ALIGN" not in html
    assert "Name" in html


@pytest.mark.django_db
def test_a_column_with_no_visible_heading_still_has_an_accessible_name():
    """An empty <th> leaves screen reader users with an unnamed column."""
    request = RequestFactory().get("/")

    html = Template(
        '{% load ui %}{% component "table" columns=columns %}'
        '<tr><td class="ui-td">x</td></tr>{% endcomponent %}'
    ).render(Context({
        "request": request,
        "columns": [{"label": "Name"}, {"label": "", "sr_label": "Row actions"}],
    }))

    assert 'class="sr-only">Row actions' in html


@pytest.mark.django_db
def test_plain_string_columns_still_work():
    request = RequestFactory().get("/")

    html = Template(
        '{% load ui %}{% component "table" columns=columns %}'
        '<tr><td class="ui-td">x</td></tr>{% endcomponent %}'
    ).render(Context({"request": request, "columns": ["Campaign", "Spend"]}))

    assert "Campaign" in html
    assert "Spend" in html
