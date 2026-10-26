from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext_lazy as _

from apps.organizations import services
from apps.organizations.models import (
    Organization,
    OrganizationMember,
    OrganizationStatus,
)


class OrganizationMemberInline(admin.TabularInline):
    model = OrganizationMember
    extra = 0
    autocomplete_fields = ["user"]
    fields = ["user", "role", "status", "job_title", "invited_by"]
    readonly_fields = ["invited_by"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """Staff-facing client administration.

    Status is read-only here for the same reason it is on accounts:
    setting it directly would skip the transition rules, the timestamp
    and the event. The actions below call the service layer.
    """

    list_display = ["name", "slug", "status", "member_count", "created_at"]
    list_filter = ["status", "country"]
    search_fields = ["name", "display_name", "slug", "email"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["status", "status_changed_at", "created_at", "updated_at"]
    inlines = [OrganizationMemberInline]
    actions = ["activate_organizations", "suspend_organizations", "archive_organizations"]

    fieldsets = (
        (None, {"fields": ("name", "display_name", "slug")}),
        (_("Contact"), {"fields": ("website", "email", "phone")}),
        (_("Address"), {"fields": ("address_line1", "address_line2", "city",
                                   "region", "postal_code", "country")}),
        (_("Status"), {
            "fields": ("status", "status_changed_at"),
            "description": _("Changed with the actions on the list, which record "
                             "the transition and publish an event."),
        }),
        (_("Internal"), {
            "fields": ("notes",),
            "description": _("Staff only. Never shown to the client."),
        }),
        (_("Dates"), {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("memberships")

    @admin.display(description=_("members"))
    def member_count(self, organization) -> int:  # noqa: ANN001
        return organization.memberships.filter(status="active").count()

    def _apply(self, request, queryset, action, verb: str) -> None:
        changed, refused = 0, 0
        for organization in queryset:
            try:
                action(organization=organization, actor=request.user,
                       reason=f"{verb} from the admin by {request.user.email}")
            except (PermissionDenied, ValidationError):
                refused += 1
            else:
                changed += 1

        if changed:
            self.message_user(request, f"{verb} {changed} organization(s).",
                              messages.SUCCESS)
        if refused:
            self.message_user(
                request,
                f"{refused} left unchanged: not permitted, or not a valid "
                "transition from their current status.",
                messages.WARNING,
            )

    @admin.action(description=_("Activate selected organizations"))
    def activate_organizations(self, request, queryset) -> None:
        self._apply(request, queryset, services.activate_organization, "Activated")

    @admin.action(description=_("Suspend selected organizations"))
    def suspend_organizations(self, request, queryset) -> None:
        self._apply(request, queryset.filter(status=OrganizationStatus.ACTIVE),
                    services.suspend_organization, "Suspended")

    @admin.action(description=_("Archive selected organizations"))
    def archive_organizations(self, request, queryset) -> None:
        self._apply(request, queryset, services.archive_organization, "Archived")


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "role", "status", "created_at"]
    list_filter = ["role", "status"]
    search_fields = ["user__email", "user__full_name", "organization__name"]
    autocomplete_fields = ["user", "organization"]
    list_select_related = ["user", "organization"]
