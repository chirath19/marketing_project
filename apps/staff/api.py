"""The staff API.

Held to the same rule as the web views, through the same `access.can()`.
Two guards again, for the same reason: `HasPlatformPermission` decides
whether the endpoint may be called, and the queryset decides which rows
come back. A permission class cannot filter rows.
"""

from __future__ import annotations

from rest_framework import mixins, serializers, viewsets

from apps.organizations.models import Organization
from apps.permissions.api import HasPlatformPermission
from apps.permissions.guards import scope_to_accessible


class OrganizationSerializer(serializers.ModelSerializer):
    label = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = ["id", "name", "display_name", "label", "slug", "status",
                  "website", "email", "phone", "city", "country",
                  "created_at", "updated_at"]
        # `notes` is absent on purpose: internal notes are staff-only in
        # both directions and must not leak through a serializer.
        read_only_fields = ["id", "slug", "status", "created_at", "updated_at"]


class OrganizationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, viewsets.GenericViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [HasPlatformPermission]
    lookup_field = "slug"

    required_permissions = {
        "GET": "organizations_view",
        "PUT": "organizations_edit",
        "PATCH": "organizations_edit",
    }

    def get_queryset(self):
        return scope_to_accessible(
            Organization.objects.all().order_by("name"),
            self.request.user, field="id",
        )
