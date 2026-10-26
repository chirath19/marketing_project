"""Attach photographs that ship with the repository to model records.

The source pictures live in `assets/images/` — unserved build input, like
the Tailwind sources beside them — at the size and format they came out
of the camera: multi-megabyte PNGs. Putting one of those on a page
unedited is the difference between a site that feels considered and one
that takes four seconds to show its hero, so nothing here copies a file
verbatim. Each picture is resized to a sane delivery width and re-encoded
as a progressive JPEG on the way in.

That matters most on the local disk backend, which serves whatever it was
given: the preset system can ask Cloudinary for a 640px crop, but it
cannot ask a file on disk to be smaller than it is. Optimising at seed
time is the one place that works for both backends.

Migrations call `attach_image()`. It is deliberately forgiving — a
deployment that ships without the assets directory, or a record an editor
has already given a picture of their own, is left exactly as it was
rather than failing the migration or overwriting someone's choice.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

#: Where the shipped originals live, relative to the project root.
SOURCE_DIR = Path("assets") / "images"

#: Long edge of the delivered file. Wide enough for a hero on a 2x
#: display once the browser has scaled it down, small enough that a page
#: carrying three of them is still a reasonable download.
MAX_WIDTH = 1800

#: Quality that survives a photograph of a screen — fine gradients and
#: small type are what JPEG handles worst, and both are in every one of
#: these pictures.
QUALITY = 82


def _optimised(source: Path) -> ContentFile | None:
    """Return `source` resized and re-encoded, or None if it cannot be read."""
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - Pillow is a hard dependency
        logger.warning("Pillow unavailable; skipping image seed for %s", source)
        return None

    try:
        with Image.open(source) as image:
            # Honour any EXIF rotation before measuring, or a portrait
            # photograph gets resized against its landscape dimensions.
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")

            if image.width > MAX_WIDTH:
                height = round(image.height * MAX_WIDTH / image.width)
                image = image.resize((MAX_WIDTH, height), Image.LANCZOS)

            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=QUALITY,
                       optimize=True, progressive=True)
    except OSError as error:
        logger.warning("Could not read %s: %s", source, error)
        return None

    return ContentFile(buffer.getvalue())


def attach_image(record, source_name: str, target_name: str, alt: str,
                 *, field: str = "image", alt_field: str = "image_alt",
                 replace: bool = False) -> bool:
    """Put `assets/images/<source_name>` on `record`, optimised.

    Returns True when the record was changed. Does nothing — and says so
    — when the source is missing or the record already carries a picture,
    unless `replace` is set, which is how a migration swaps an earlier
    unoptimised copy for a smaller one.
    """
    if record is None:
        return False

    existing = getattr(record, field, None)
    if existing and not replace:
        return False

    source = Path(settings.BASE_DIR) / SOURCE_DIR / source_name
    if not source.is_file():
        logger.info("No source image at %s; leaving %r unchanged", source, record)
        return False

    content = _optimised(source)
    if content is None:
        return False

    if existing:
        # Drop the old file rather than orphaning it in the media store.
        existing.delete(save=False)

    getattr(record, field).save(target_name, content, save=False)
    if alt_field:
        setattr(record, alt_field, alt)
    return True


def detach_image(record, target_stem: str, *, field: str = "image",
                 alt_field: str = "image_alt") -> bool:
    """Remove a picture this module attached, leaving an editor's alone.

    The filename is the only evidence of where a picture came from, so a
    reversal only touches a file still named the way `attach_image` named
    it.
    """
    if record is None:
        return False

    existing = getattr(record, field, None)
    if not existing or not Path(existing.name).stem.startswith(target_stem):
        return False

    existing.delete(save=False)
    setattr(record, field, "")
    if alt_field:
        setattr(record, alt_field, "")
    return True
