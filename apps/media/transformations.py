"""Named image presets.

Templates ask for a preset ("card"), never for pixel dimensions. That
keeps every image on the site inside a known set of sizes, which is what
makes a CDN cache useful and stops one stray template requesting a
4000px hero.

The presets are provider-neutral. The local backend ignores them and
serves the original; the Cloudinary backend turns them into delivery
transformations. Calling code is identical either way.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Preset:
    width: int
    height: int | None = None
    crop: str = "limit"
    gravity: str | None = None


PRESETS: dict[str, Preset] = {
    "avatar": Preset(width=96, height=96, crop="fill", gravity="face"),
    "thumb": Preset(width=160, height=160, crop="fill"),
    "card": Preset(width=640, height=400, crop="fill"),
    "wide": Preset(width=1024),
    "hero": Preset(width=1920, height=900, crop="fill"),
    "original": Preset(width=0),
}

# Widths offered in a srcset, so one <img> serves phone through desktop.
RESPONSIVE_WIDTHS: tuple[int, ...] = (320, 640, 960, 1280, 1920)

DEFAULT_PRESET = "wide"


def get_preset(name: str) -> Preset:
    return PRESETS.get(name, PRESETS[DEFAULT_PRESET])
