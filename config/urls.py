"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    # Infrastructure. Deliberately not under /admin so a healthcheck never
    # depends on the admin app being reachable.
    path("healthz", core_views.health, name="health"),

    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("notifications/", include("apps.notifications.urls", namespace="notifications")),
    path("organization/", include("apps.organizations.urls", namespace="organizations")),
    path("staff/", include("apps.staff.urls", namespace="staff")),
    path("api/v1/", include("config.api_urls", namespace="api")),
    path("t/", include("apps.tracking.urls", namespace="tracking")),
    path("", include("apps.core.urls", namespace="core")),

    # The public website. Registered last so its catch-all page route
    # cannot shadow an application path.
    path("", include("apps.cms.urls", namespace="public")),
]

# Branded error pages.
handler400 = "apps.core.views.bad_request"
handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"

if settings.DEBUG:
    # Only the dev server serves user uploads directly; in production this
    # is WhiteNoise for static and the media backend for uploads.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    if "debug_toolbar" in settings.INSTALLED_APPS:
        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
