from django.contrib import admin
from django.contrib.auth.models import Permission
from django.utils.translation import gettext_lazy as _

from apps.permissions.models import Role, RolePermission, UserPermissionOverride


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """Django's Permission model, registered so it can be autocompleted.

    Read-only: permissions are declared in `catalogue.py` and created by
    `sync_permissions`. Adding one by hand here would produce a right that
    no code ever checks.
    """

    list_display = ["codename", "name", "content_type"]
    search_fields = ["codename", "name"]
    list_filter = ["content_type__app_label"]
    list_select_related = ["content_type"]

    def get_queryset(self, request):
        # The catalogue first, since that is what roles are built from.
        return super().get_queryset(request).order_by(
            "content_type__app_label", "codename"
        )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0
    autocomplete_fields = ["permission"]
    readonly_fields = ["granted_by"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "permission_count", "is_system", "updated_at"]
    list_filter = ["is_system"]
    search_fields = ["name", "description"]
    prepopulated_fields = {"slug": ("name",)}
    inlines = [RolePermissionInline]

    @admin.display(description=_("permissions"))
    def permission_count(self, role) -> int:  # noqa: ANN001
        return role.permissions.count()

    def has_delete_permission(self, request, obj=None) -> bool:
        # System roles ship with the platform; deleting one would silently
        # strip every staff member who holds it.
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(UserPermissionOverride)
class UserPermissionOverrideAdmin(admin.ModelAdmin):
    list_display = ["user", "permission", "effect", "reason", "granted_by",
                    "created_at"]
    list_filter = ["effect"]
    search_fields = ["user__email", "permission__codename", "reason"]
    autocomplete_fields = ["user", "permission"]
    list_select_related = ["user", "permission", "granted_by"]
