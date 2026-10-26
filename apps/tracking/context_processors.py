"""Tracking settings for every template.

Resolved lazily — the staff dashboard, the API and the health check never
pay for this query, since `SimpleLazyObject` only resolves on first
attribute access and none of those templates mention `tracking_settings`.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject


def tracking_settings(request: HttpRequest) -> dict:
    def current():  # noqa: ANN202
        from apps.core.features import enabled
        from apps.tracking.models import TrackingSettings

        settings = TrackingSettings.objects.current()
        for key, fields in {
            "gtm": ["gtm_container_id"], "ga4": ["ga4_measurement_id"],
            "meta_pixel": ["meta_pixel_id"],
            "rudderstack": ["rudderstack_write_key", "rudderstack_data_plane_url"],
        }.items():
            if not enabled(key, operating=request.operating):
                for field in fields:
                    setattr(settings, field, "")
        return settings

    return {"tracking_settings": SimpleLazyObject(current)}
