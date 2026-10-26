from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.staff.models import StaffClientAssignment, StaffProfile


class StaffClientAssignmentInline(admin.TabularInline):
    model = StaffClientAssignment
    extra = 0
    autocomplete_fields = ["organization"]
    fields = ["organization", "role", "status", "is_primary", "assigned_by"]
    readonly_fields = ["assigned_by"]


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "job_title", "department", "role_list",
                    "has_all_client_access", "client_count"]
    list_filter = ["has_all_client_access", "department", "roles"]
    search_fields = ["user__email", "user__full_name", "job_title"]
    autocomplete_fields = ["user"]
    filter_horizontal = ["roles"]
    inlines = [StaffClientAssignmentInline]
    list_select_related = ["user"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("roles", "assignments")

    @admin.display(description=_("roles"))
    def role_list(self, profile) -> str:  # noqa: ANN001
        return ", ".join(profile.role_names) or "—"

    @admin.display(description=_("clients"))
    def client_count(self, profile) -> str:  # noqa: ANN001
        if profile.has_all_client_access:
            return "all"
        return str(profile.assignments.filter(status="active").count())


@admin.register(StaffClientAssignment)
class StaffClientAssignmentAdmin(admin.ModelAdmin):
    list_display = ["staff", "organization", "role", "status", "is_primary",
                    "created_at"]
    list_filter = ["role", "status", "is_primary"]
    search_fields = ["staff__user__email", "organization__name"]
    autocomplete_fields = ["staff", "organization"]
    list_select_related = ["staff__user", "organization"]
