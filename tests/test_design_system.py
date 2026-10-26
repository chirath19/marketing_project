"""Guards on the design system.

The phase brief asks for reusable tokens, consistent spacing and
typography, and no feature-specific one-off styling where a component
exists. Those are easy to state and easy to erode, so they are tests.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

BASE_DIR = Path(settings.BASE_DIR)
TEMPLATE_DIR = BASE_DIR / "templates"
COMPONENT_DIR = TEMPLATE_DIR / "components"
CSS = BASE_DIR / "assets" / "css" / "app.css"

BRAND_HEXES = ["#111C38", "#233457", "#E4A33C", "#6E7B96", "#EEF1F6"]

# The styleguide names the palette on screen and the standalone 500 page
# cannot load the stylesheet, so both legitimately contain hex values.
HEX_EXEMPT = {"styleguide.html", "500.html"}

PAGE_TEMPLATES = [
    p for p in TEMPLATE_DIR.rglob("*.html")
    if "components" not in p.relative_to(TEMPLATE_DIR).parts
]


def test_the_brand_palette_is_defined_once_as_tokens():
    css = CSS.read_text()

    for hex_value in BRAND_HEXES:
        assert hex_value in css, f"{hex_value} is not defined in the token block"


@pytest.mark.parametrize("path", PAGE_TEMPLATES, ids=lambda p: p.name)
def test_page_templates_use_tokens_rather_than_raw_hex(path):
    """A hex value in a page template is a colour decision made outside
    the design system, and the next page will make a different one."""
    if path.name in HEX_EXEMPT:
        pytest.skip("names the palette on screen, or cannot load the stylesheet")

    found = re.findall(r"#[0-9A-Fa-f]{6}\b", path.read_text())

    assert not found, f"{path.name} hardcodes {found}"


@pytest.mark.parametrize("path", sorted(COMPONENT_DIR.rglob("*.html")), ids=lambda p: p.name)
def test_components_use_tokens_rather_than_raw_hex(path):
    found = re.findall(r"#[0-9A-Fa-f]{6}\b", path.read_text())

    assert not found, f"{path.name} hardcodes {found}"


def test_the_shared_control_classes_are_defined_in_one_place():
    """apps.core.forms sets these on widget attrs and the standalone
    control templates write them in markup. If the stylesheet stopped
    defining one, both would silently render unstyled."""
    css = CSS.read_text()

    for name in ("ui-input", "ui-select", "ui-checkbox", "ui-radio",
                 "ui-label", "ui-help", "ui-error", "ui-th", "ui-td",
                 "ui-menu-item", "ui-skeleton", "ui-backdrop", "ui-panel"):
        assert f".{name}" in css, f"{name} is referenced in markup but not defined"


def test_the_typography_scale_is_defined():
    css = CSS.read_text()

    for name in ("t-eyebrow", "t-page-title", "t-section", "t-card-title",
                 "t-body", "t-meta", "t-micro"):
        assert f".{name}" in css


def test_the_form_mixin_and_the_stylesheet_agree_on_class_names():
    from apps.core.forms import CONTROL_CLASSES

    css = CSS.read_text()
    for value in CONTROL_CLASSES.values():
        for name in value.split():
            if name.startswith("ui-"):
                assert f".{name}" in css, f"{name} is applied to widgets but undefined"


def test_responsive_table_stacking_is_defined_once_in_css():
    """The alternative — a second markup path for small screens — doubles
    the work and drifts."""
    css = CSS.read_text()

    assert ".ui-table-stack" in css
    assert "data-label" in css


def test_stacking_order_is_tokenised():
    """Overlays are the classic source of z-index arms races."""
    css = CSS.read_text()

    for token in ("--z-sticky", "--z-dropdown", "--z-drawer", "--z-modal", "--z-toast"):
        assert token in css


def test_reduced_motion_is_respected():
    assert "prefers-reduced-motion" in CSS.read_text()


# --- every tag resolves to a real template ---------------------------------


def component_templates_referenced_by_tags() -> list[str]:
    import inspect

    from apps.core.templatetags import ui

    names = []
    for value in vars(ui).values():
        source = getattr(value, "__wrapped__", None) or value
        if not callable(source) or getattr(source, "__module__", "") != ui.__name__:
            continue
        try:
            code = inspect.getsource(source)
        except (OSError, TypeError):
            continue
        names.extend(re.findall(r'"(components/[\w/]+\.html)"', code))
    return sorted(set(names))


@pytest.mark.parametrize("template_name", component_templates_referenced_by_tags())
def test_every_tag_points_at_a_template_that_exists(template_name):
    try:
        get_template(template_name)
    except TemplateDoesNotExist:  # pragma: no cover - the assertion reports it
        pytest.fail(f"{template_name} is referenced by a tag but does not exist")


def test_the_theme_colour_setting_matches_the_navy_token():
    """A <meta> tag cannot read a CSS custom property, so the brand navy
    exists in two places. This is the test that keeps them equal."""
    from django.conf import settings as django_settings

    css = CSS.read_text()
    declared = re.search(r"--color-navy:\s*(#[0-9A-Fa-f]{6})", css)

    assert declared, "--color-navy is not defined"
    assert django_settings.SITE_THEME_COLOR.lower() == declared.group(1).lower()
