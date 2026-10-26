"""Media abstraction: the point is that calling code never changes when
the backend does."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template import Context, Template

from apps.media.storages import (
    CloudinaryMediaStorage,
    cloudinary_is_configured,
    configure_cloudinary,
)
from apps.media.transformations import PRESETS, get_preset


def render(template_string: str, **context) -> str:
    return Template("{% load media_tags %}" + template_string).render(Context(context))


# --- presets ---------------------------------------------------------------


def test_every_preset_defines_a_width_or_is_the_passthrough():
    for name, preset in PRESETS.items():
        assert preset.width >= 0, name
        if name != "original":
            assert preset.width > 0, name


def test_an_unknown_preset_falls_back_instead_of_raising():
    """A typo in a template must not take a page down."""
    assert get_preset("enormous") is PRESETS["wide"]


# --- configuration ---------------------------------------------------------


def test_cloudinary_is_not_considered_configured_without_credentials(settings):
    settings.CLOUDINARY = {"CLOUD_NAME": "", "API_KEY": "", "API_SECRET": ""}

    assert not cloudinary_is_configured()


def test_configuring_cloudinary_without_credentials_fails_loudly(settings):
    """Better a startup error than silently writing uploads nowhere."""
    settings.CLOUDINARY = {"CLOUD_NAME": "", "API_KEY": "", "API_SECRET": ""}

    with pytest.raises(ImproperlyConfigured, match="CLOUDINARY_CLOUD_NAME"):
        configure_cloudinary()


# --- URL building ----------------------------------------------------------


@pytest.fixture
def cloudinary_storage(settings):
    settings.CLOUDINARY = {
        "CLOUD_NAME": "demo-cloud",
        "API_KEY": "123456789",
        "API_SECRET": "test-secret",
        "SECURE": True,
        "FOLDER": "heliograph",
    }
    configure_cloudinary()
    return CloudinaryMediaStorage()


def test_cloudinary_url_is_https_and_names_the_cloud(cloudinary_storage):
    url = cloudinary_storage.url("heliograph/team-photo")

    assert url.startswith("https://")
    assert "demo-cloud" in url
    assert "team-photo" in url


def test_a_preset_becomes_a_delivery_transformation(cloudinary_storage):
    url = cloudinary_storage.url("heliograph/team-photo", preset="card")

    assert "w_640" in url
    assert "h_400" in url
    assert "c_fill" in url
    assert "q_auto" in url
    assert "f_auto" in url


def test_the_original_preset_applies_no_transformation(cloudinary_storage):
    url = cloudinary_storage.url("heliograph/team-photo", preset="original")

    assert "w_" not in url


def test_a_srcset_width_keeps_the_presets_aspect_ratio(cloudinary_storage):
    """Re-targeting a 640x400 preset to 320px must give 320x200, not a
    320-wide image squashed into a 400px box."""
    url = cloudinary_storage.url("heliograph/team-photo", preset="card", width=320)

    assert "w_320" in url
    assert "h_200" in url


def test_the_public_id_drops_the_extension_and_keeps_the_folder():
    storage = CloudinaryMediaStorage(folder="heliograph")

    assert storage._public_id("uploads/photo.jpg") == "heliograph/uploads/photo"


# --- template tags ---------------------------------------------------------


def test_media_img_renders_nothing_for_an_empty_value():
    assert render("{% media_img photo %}", photo=None).strip() == ""


def test_media_img_against_local_storage_emits_no_srcset():
    """Local disk holds one file at one size. Advertising five widths for
    it would be a lie to the browser."""
    name = default_storage.save("test-local.txt", ContentFile(b"x"))
    try:
        html = render("{% media_img photo preset='card' alt='A' %}", photo=name)

        assert "srcset" not in html
        assert 'alt="A"' in html
    finally:
        default_storage.delete(name)


def test_media_img_sets_dimensions_and_lazy_loading():
    name = default_storage.save("test-dims.txt", ContentFile(b"x"))
    try:
        html = render("{% media_img photo preset='card' %}", photo=name)

        assert 'width="640"' in html
        assert 'height="400"' in html
        assert 'loading="lazy"' in html
        assert 'decoding="async"' in html
    finally:
        default_storage.delete(name)


def test_media_img_against_cloudinary_emits_distinct_srcset_widths(
    cloudinary_storage, monkeypatch
):
    import apps.media.templatetags.media_tags as tags

    monkeypatch.setattr(tags, "default_storage", cloudinary_storage)

    html = render("{% media_img photo preset='card' alt='Team' %}",
                  photo="heliograph/team")

    assert "srcset" in html
    assert "320w" in html
    assert "640w" in html
    # Each candidate must be a genuinely different URL, or the srcset is
    # pointless weight on the page.
    assert "w_320" in html
    assert "w_640" in html
    assert "1920w" not in html, "must not upscale beyond the preset"
