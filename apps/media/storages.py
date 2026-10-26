"""Storage backends.

`MEDIA_BACKEND=local` writes to disk; `MEDIA_BACKEND=cloudinary` sends the
same calls to Cloudinary. Nothing above this module knows which is in
use — models declare plain `FileField`/`ImageField` and Django's
`STORAGES["default"]` decides.
"""

from __future__ import annotations

import logging
import posixpath
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from apps.media.transformations import Preset, get_preset

logger = logging.getLogger(__name__)


def cloudinary_is_configured() -> bool:
    config = getattr(settings, "CLOUDINARY", {})
    return all(config.get(key) for key in ("CLOUD_NAME", "API_KEY", "API_SECRET"))


def configure_cloudinary() -> None:
    """Apply credentials to the Cloudinary SDK from settings.

    Called once from the app's `ready()`. Credentials come from the
    environment; none are ever written in source.
    """
    if not cloudinary_is_configured():
        raise ImproperlyConfigured(
            "MEDIA_BACKEND=cloudinary requires CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET to be set."
        )

    import cloudinary

    config = settings.CLOUDINARY
    cloudinary.config(
        cloud_name=config["CLOUD_NAME"],
        api_key=config["API_KEY"],
        api_secret=config["API_SECRET"],
        secure=config.get("SECURE", True),
    )


def _transformation(preset: Preset, width: int | None = None) -> dict[str, Any]:
    """Build delivery options for a preset, optionally re-targeted to a width.

    `width` is used to generate srcset candidates: the preset's crop and
    gravity are kept, but the height is dropped so the aspect ratio is
    preserved rather than the image being squashed into the preset's box
    at the wrong scale.
    """
    effective_width = width or preset.width
    if not effective_width:
        return {}

    options: dict[str, Any] = {
        "width": effective_width,
        "crop": preset.crop,
        "quality": "auto",
        "fetch_format": "auto",
    }
    if preset.height and width is None:
        options["height"] = preset.height
    elif preset.height and width is not None:
        # Keep the preset's shape at the requested width.
        options["height"] = round(width * preset.height / preset.width)
    if preset.gravity:
        options["gravity"] = preset.gravity
    return options


@deconstructible
class CloudinaryMediaStorage(Storage):
    """A minimal Cloudinary storage backend.

    Written directly against the official SDK rather than pulling in a
    third-party Django integration: the available one has not tracked
    recent Django releases, and the surface we need is small enough that
    owning it is cheaper than inheriting that risk.
    """

    #: Templates emit a srcset only against a backend that can actually
    #: resize. The local backend has one file and one size.
    supports_transformations = True

    def __init__(self, folder: str | None = None, resource_type: str = "auto") -> None:
        self.folder = folder if folder is not None else settings.CLOUDINARY.get("FOLDER", "")
        self.resource_type = resource_type

    # --- helpers ---

    def _public_id(self, name: str) -> str:
        name = name.lstrip("/")
        base, _dot, _ext = name.rpartition(".")
        stem = base or name
        return posixpath.join(self.folder, stem) if self.folder else stem

    # --- Storage API ---

    def _save(self, name: str, content: File) -> str:
        import cloudinary.uploader

        result = cloudinary.uploader.upload(
            content,
            public_id=self._public_id(name),
            resource_type=self.resource_type,
            overwrite=False,
            unique_filename=True,
            use_filename=True,
            invalidate=True,
        )
        # The returned public_id is authoritative: Cloudinary may have
        # made the name unique.
        return result["public_id"]

    def _open(self, name: str, mode: str = "rb") -> File:
        """Fetch a stored asset back over HTTPS.

        Uses the standard library rather than `requests`, which the
        Cloudinary SDK does not depend on — importing it here would work
        on a machine that happened to have it and fail on a clean deploy.
        """
        from urllib.request import urlopen

        from django.core.files.base import ContentFile

        with urlopen(self.url(name), timeout=30) as response:  # noqa: S310
            return ContentFile(response.read(), name=name)

    def delete(self, name: str) -> None:
        import cloudinary.uploader

        try:
            cloudinary.uploader.destroy(name, resource_type=self.resource_type,
                                        invalidate=True)
        except Exception:
            # A failed remote delete must not break the request that
            # removed the database row; it is reconciled by housekeeping.
            logger.exception("Cloudinary delete failed for %s", name)

    def exists(self, name: str) -> bool:
        # Always False so Django does not probe the remote API on every
        # upload. Uniqueness is Cloudinary's job (`unique_filename`).
        return False

    def url(self, name: str, preset: str = "original",
            width: int | None = None) -> str:
        from cloudinary.utils import cloudinary_url

        built, _options = cloudinary_url(
            name,
            resource_type=self.resource_type if self.resource_type != "auto" else "image",
            secure=settings.CLOUDINARY.get("SECURE", True),
            **_transformation(get_preset(preset), width),
        )
        return built

    def size(self, name: str) -> int:
        import cloudinary.api

        try:
            return int(cloudinary.api.resource(name)["bytes"])
        except Exception:
            logger.exception("Cloudinary size lookup failed for %s", name)
            return 0
