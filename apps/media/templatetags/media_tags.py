"""Image tags.

`{% media_img photo preset="card" alt="Team photo" %}` emits a responsive
`<img>` with explicit dimensions (so the browser reserves space and the
page does not shift while loading) and lazy loading by default.
Templates never build a media URL by hand.

A `srcset` is emitted only when the active storage backend can actually
produce different sizes. Against local disk there is one file at one
size, and advertising five widths for it would just be a lie to the
browser.
"""

from __future__ import annotations

from django import template
from django.core.files.storage import default_storage

from apps.media.transformations import RESPONSIVE_WIDTHS, get_preset

register = template.Library()


def _resolve(file_or_name):  # noqa: ANN001, ANN201
    name = getattr(file_or_name, "name", file_or_name)
    storage = getattr(file_or_name, "storage", None) or default_storage
    return name, storage


def _url(file_or_name, preset: str = "original",  # noqa: ANN001
         width: int | None = None) -> str:
    if not file_or_name:
        return ""

    name, storage = _resolve(file_or_name)
    if getattr(storage, "supports_transformations", False):
        return storage.url(name, preset=preset, width=width)
    return storage.url(name)


@register.simple_tag
def media_url(file_or_name, preset: str = "original") -> str:  # noqa: ANN001
    return _url(file_or_name, preset)


@register.inclusion_tag("components/image.html")
def media_img(file_or_name, alt: str = "", preset: str = "wide",  # noqa: ANN001
              sizes: str = "100vw", css_class: str = "", loading: str = "lazy",
              fetchpriority: str = "auto") -> dict:
    spec = get_preset(preset)
    src = _url(file_or_name, preset)

    srcset = ""
    if src and spec.width:
        _name, storage = _resolve(file_or_name)
        if getattr(storage, "supports_transformations", False):
            widths = [w for w in RESPONSIVE_WIDTHS if w <= spec.width] or [spec.width]
            srcset = ", ".join(
                f"{_url(file_or_name, preset, width=w)} {w}w" for w in widths
            )

    height = spec.height
    return {
        "src": src,
        "srcset": srcset,
        "sizes": sizes if srcset else "",
        "alt": alt,
        "width": spec.width or None,
        "height": height,
        "css_class": css_class,
        "loading": loading,
        "fetchpriority": fetchpriority,
    }
