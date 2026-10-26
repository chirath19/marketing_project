"""The API root.

Secondary to the server-rendered dashboards, and held to the same
authorisation rules — see `apps.permissions.api`.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.staff.api import OrganizationViewSet

router = DefaultRouter()
router.register("organizations", OrganizationViewSet, basename="organization")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
]
