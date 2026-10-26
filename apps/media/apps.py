from django.apps import AppConfig
from django.conf import settings


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.media"
    label = "media"
    verbose_name = "Media"

    def ready(self) -> None:
        # Configure the SDK once, at startup, only when it is the active
        # backend — so a local or CI environment needs no Cloudinary
        # credentials at all.
        if getattr(settings, "MEDIA_BACKEND", "local") == "cloudinary":
            from apps.media.storages import configure_cloudinary

            configure_cloudinary()
