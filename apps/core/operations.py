"""Owner-controlled operating mode; disabled features retain their data."""

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotFound
from django.utils.functional import SimpleLazyObject

from apps.core.models import OperatingSettings


def current():
    return OperatingSettings.objects.get_or_create(pk=1)[0]


def update(*, actor, values):
    if not actor.is_active or not actor.is_super_admin:
        raise PermissionDenied
    from django.core.exceptions import ValidationError

    from apps.core.features import FEATURES, MASTER_FIELDS

    flags = values.get("feature_flags", {})
    if not isinstance(flags, dict) or any(
        key not in FEATURES or key in MASTER_FIELDS or not isinstance(value, bool)
        for key, value in flags.items()
    ):
        raise ValidationError("Use known feature names with true or false values.")
    obj = current()
    for key in (
        "integrations_enabled",
        "api_enabled",
        "analytics_enabled",
        "show_public_prices",
        "require_quote_account",
        "feature_flags",
    ):
        if key in values:
            setattr(obj, key, values[key])
    obj.full_clean()
    obj.save()
    return obj


class OperatingModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.operating = SimpleLazyObject(current)
        if request.path.startswith("/api/") and not request.operating.api_enabled:
            return HttpResponseNotFound("The API is disabled by the website owner.")
        if request.path.startswith("/t/") and not request.operating.analytics_enabled:
            return HttpResponseNotFound("Analytics are disabled.")
        return self.get_response(request)

    def process_view(self, request, view, args, kwargs):
        from apps.core.features import route_feature, visible

        if request.user.is_authenticated:
            request.user._operating_settings = request.operating
        key = route_feature(request, kwargs)
        if key and not visible(key, request.user, operating=request.operating):
            return HttpResponseNotFound("This feature is not available.")

        return None
