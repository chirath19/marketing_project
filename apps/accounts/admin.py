from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts import services
from apps.accounts.models import AccountStatus, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Staff-facing account administration.

    Status is not an editable field here. Setting it directly would skip
    the transition rules, the reason, the timestamp and the event — so it
    is read-only, and the three actions below call the service layer,
    which records all of them.
    """

    ordering = ["email"]
    list_display = ["email", "full_name", "user_type",
                    "status", "is_staff", "date_joined"]
    list_filter = ["status", "user_type", "is_staff", "is_superuser"]
    search_fields = ["email", "full_name"]
    readonly_fields = ["last_login", "date_joined", "status",
                       "status_changed_at", "status_reason"]
    actions = ["approve_accounts", "suspend_accounts", "reactivate_accounts"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Profile"), {"fields": ("full_name", "phone",
                                   "job_title", "user_type")}),
        (_("Account status"), {
            "fields": ("status", "status_changed_at", "status_reason"),
            "description": _(
                "Changed with the actions on the account list, which record "
                "who made the change and why."
            ),
        }),
        (_("Permissions"), {
            "fields": ("is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        (_("Dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "user_type",
                       "password1", "password2"),
        }),
    )

    def _apply(self, request, queryset, action, verb: str) -> None:
        changed, refused = 0, 0
        for user in queryset:
            try:
                action(user=user, actor=request.user,
                       reason=f"{verb} from the admin by {request.user.email}")
            except (PermissionDenied, ValidationError):
                refused += 1
            else:
                changed += 1

        if changed:
            self.message_user(request, f"{verb} {changed} account(s).",
                              messages.SUCCESS)
        if refused:
            self.message_user(
                request,
                f"{refused} account(s) were left unchanged: not permitted, or "
                "not a valid transition from their current status.",
                messages.WARNING,
            )

    @admin.action(description=_("Approve selected pending accounts"))
    def approve_accounts(self, request, queryset) -> None:
        self._apply(request, queryset.filter(status=AccountStatus.PENDING),
                    services.approve_account, "Approved")

    @admin.action(description=_("Suspend selected accounts"))
    def suspend_accounts(self, request, queryset) -> None:
        self._apply(request, queryset.filter(status=AccountStatus.ACTIVE),
                    services.suspend_account, "Suspended")

    @admin.action(description=_("Reactivate selected suspended accounts"))
    def reactivate_accounts(self, request, queryset) -> None:
        self._apply(request, queryset.filter(status=AccountStatus.SUSPENDED),
                    services.reactivate_account, "Reactivated")
