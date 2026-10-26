"""The design vocabulary, tested without rendering anything."""

import pytest
from django.db import models

from apps.core import design


class Status(models.TextChoices):
    LIVE = "live", "Live"
    PAUSED = "paused", "Paused"


# --- status tones ----------------------------------------------------------


def test_a_text_choices_member_maps_to_its_tone():
    assert design.tone_for_status(Status.LIVE) == "live"
    assert design.tone_for_status(Status.PAUSED) == "paused"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("live", "live"), ("LIVE", "live"), (" Live ", "live"),
     ("awaiting approval", "paused"), ("awaiting_approval", "paused"),
     ("cancelled", "danger"), ("done", "done")],
)
def test_status_strings_are_normalised_before_lookup(value, expected):
    """Callers pass whatever their domain uses; the mapping copes."""
    assert design.tone_for_status(value) == expected


def test_an_unknown_status_is_neutral_not_unstyled():
    assert design.tone_for_status("something-new") == "neutral"


def test_a_missing_status_is_neutral():
    assert design.tone_for_status(None) == "neutral"


# --- buttons ---------------------------------------------------------------


def test_button_classes_compose_base_variant_and_size():
    css = design.button_classes("danger", "lg")

    assert "bg-danger" in css
    assert "px-5" in css
    assert "focus-ring" in css


def test_an_unknown_button_variant_falls_back_to_primary():
    assert "bg-gold" in design.button_classes("chartreuse")


def test_an_icon_button_is_square_rather_than_padded():
    css = design.button_classes(size="md", icon_only=True)

    assert "h-9 w-9" in css
    assert "px-4" not in css


def test_a_full_width_button_is_marked_as_such():
    assert "w-full" in design.button_classes(full=True)


# --- alerts ----------------------------------------------------------------


def test_errors_interrupt_and_information_waits():
    """`alert` preempts a screen reader; `status` lets it finish first.
    Getting this backwards makes a page either rude or silent."""
    _css, role = design.alert_tone("danger")
    assert role == "alert"

    _css, role = design.alert_tone("info")
    assert role == "status"


def test_djangos_error_tag_is_mapped_rather_than_falling_back():
    css, role = design.alert_tone("error")

    assert "text-danger" in css
    assert role == "alert"


# --- metrics ---------------------------------------------------------------


def test_direction_decides_tone_not_the_sign_of_the_number():
    good_css, _ = design.delta_style("good")
    bad_css, _ = design.delta_style("bad")

    assert good_css == "text-live"
    assert bad_css == "text-danger"


def test_an_unknown_direction_is_neutral():
    css, arrow = design.delta_style("sideways")

    assert css == "text-steel"
    assert arrow == "→"


@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [(412, 450, 91.6), (0, 450, 0.0), (450, 450, 100.0),
     (500, 450, 100.0), (-10, 450, 0.0)],
)
def test_percentage_is_clamped(current, target, expected):
    assert design.percentage(current, target) == expected


@pytest.mark.parametrize("target", [0, None, "", "many"])
def test_percentage_survives_a_useless_target(target):
    """A goal nobody set must not take the page down."""
    assert design.percentage(10, target) == 0.0


def test_classes_drops_empty_fragments():
    assert design.classes("a", "", None, "b") == "a b"


# --- status labels ---------------------------------------------------------


def test_a_text_choices_label_is_used_verbatim():
    assert design.status_label(Status.LIVE) == "Live"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("live", "Live"), ("awaiting_approval", "Awaiting approval"),
     ("on-hold", "On hold"), ("DONE", "DONE")],
)
def test_a_raw_status_string_is_humanised(value, expected):
    """`awaiting_approval` is not something to show a client."""
    assert design.status_label(value) == expected


def test_a_missing_status_reads_as_unknown_rather_than_blank():
    assert design.status_label(None) == "Unknown"
    assert design.status_label("") == "Unknown"
