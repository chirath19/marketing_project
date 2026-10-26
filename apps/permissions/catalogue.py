"""The platform's permission vocabulary.

Every granular right is a (module, action) pair. The catalogue below is
the single declaration of which pairs exist; a management command turns
it into real `django.contrib.auth.Permission` rows, and a test fails the
build if the two drift apart.

Why Django's `Permission` model rather than a parallel table: it makes
`user.has_perm("permissions.seo_edit")` work, which in turn makes
`@permission_required`, `{% if perms.permissions.seo_edit %}`, DRF's
permission classes and the Django admin all work without adapters. The
parts Django does not provide — a deny override, and "permission AND
access to this client" — are added by the backend, not by replacing what
is already there.

Permission strings are `permissions.<module>_<action>`, for example
`permissions.seo_edit`. They all live under the `permissions` app label
so that one content type carries the catalogue and the module stays
visible in the codename.
"""

from __future__ import annotations

from dataclasses import dataclass

APP_LABEL = "permissions"

#: The content type the catalogue's permissions hang off. Django also
#: auto-creates add/change/delete/view permissions for this app's own
#: models (Role, RolePermission, UserPermissionOverride) under the same
#: app label, so every lookup filters on this model name too — otherwise
#: `add_role` would be resolved as if it were a platform permission.
CONTENT_TYPE_MODEL = "platformpermission"


class Action:
    """The operations a permission can grant."""

    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    PUBLISH = "publish"
    APPROVE = "approve"
    ASSIGN = "assign"
    EXPORT = "export"
    MANAGE = "manage"


ACTION_LABELS = {
    Action.VIEW: "View",
    Action.CREATE: "Create",
    Action.EDIT: "Edit",
    Action.DELETE: "Delete",
    Action.PUBLISH: "Publish",
    Action.APPROVE: "Approve",
    Action.ASSIGN: "Assign",
    Action.EXPORT: "Export",
    Action.MANAGE: "Manage",
}

ALL_ACTIONS = tuple(ACTION_LABELS)

#: Read-only work: look at it, and take a copy away.
READ_ACTIONS = (Action.VIEW, Action.EXPORT)

#: Ordinary delivery work on a module.
DELIVERY_ACTIONS = (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE,
                    Action.APPROVE, Action.EXPORT)

#: Content that goes live.
PUBLISHING_ACTIONS = (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE,
                      Action.PUBLISH, Action.EXPORT)


@dataclass(frozen=True, slots=True)
class Module:
    """An area of the platform that permissions are granted over."""

    key: str
    label: str
    actions: tuple[str, ...]
    #: Whether rights over this module are scoped to assigned clients.
    #: Platform-wide areas (staff administration, system settings) are
    #: not: they do not belong to any one client.
    client_scoped: bool = True
    description: str = ""


MODULES: tuple[Module, ...] = (
    # --- client delivery -------------------------------------------------
    Module("campaigns", "Campaigns",
           (*DELIVERY_ACTIONS, Action.ASSIGN),
           description="Campaign records across every service."),
    Module("seo", "SEO", DELIVERY_ACTIONS),
    Module("paid_ads", "Paid ads", DELIVERY_ACTIONS),
    Module("social", "Social media", PUBLISHING_ACTIONS),
    Module("email_marketing", "Email marketing", PUBLISHING_ACTIONS),
    Module("analytics", "Analytics and reporting",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.EXPORT)),
    Module("approvals", "Client approvals",
           (Action.VIEW, Action.CREATE, Action.APPROVE, Action.EXPORT)),
    Module("messaging", "Client messaging",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)),
    Module("media", "Media library", DELIVERY_ACTIONS),

    # --- commercial -------------------------------------------------------
    Module("leads", "Leads and enquiries",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE,
            Action.ASSIGN, Action.EXPORT)),
    Module("quotes", "Quote requests",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE,
            Action.APPROVE, Action.ASSIGN, Action.EXPORT),
           description="Requests built from the service catalogue."),
    Module("notifications", "Notifications",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE)),
    Module("subscriptions", "Subscriptions",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE,
            Action.APPROVE, Action.EXPORT)),
    Module("organizations", "Client organizations",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.ASSIGN,
            Action.EXPORT, Action.MANAGE)),

    # --- platform-wide ----------------------------------------------------
    Module("catalog", "Service catalogue", PUBLISHING_ACTIONS,
           client_scoped=False,
           description="The services offered. Not owned by any one client."),
    Module("cms", "Website content", PUBLISHING_ACTIONS, client_scoped=False),
    Module("blog", "Blog", PUBLISHING_ACTIONS, client_scoped=False,
           description="Articles on the public site."),
    Module("staff", "Staff administration",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE,
            Action.ASSIGN, Action.MANAGE),
           client_scoped=False),
    Module("roles", "Roles and permissions",
           (Action.VIEW, Action.CREATE, Action.EDIT, Action.DELETE, Action.MANAGE),
           client_scoped=False),
    Module("settings", "System settings",
           (Action.VIEW, Action.EDIT, Action.MANAGE), client_scoped=False),
    Module("integrations", "Integration settings",
           (Action.VIEW, Action.EDIT, Action.MANAGE), client_scoped=False),
    Module("audit", "Audit log", READ_ACTIONS, client_scoped=False),
)

MODULES_BY_KEY: dict[str, Module] = {module.key: module for module in MODULES}


def codename(module: str, action: str) -> str:
    """`seo_edit` — the Permission row's codename."""
    return f"{module}_{action}"


def permission_string(module: str, action: str) -> str:
    """`permissions.seo_edit` — what `has_perm` is called with."""
    return f"{APP_LABEL}.{codename(module, action)}"


def split_codename(value: str) -> tuple[str, str] | None:
    """Turn a codename back into (module, action), or None if unknown.

    Module keys contain underscores (`paid_ads`, `email_marketing`), so
    the split is driven by the known modules rather than by `rsplit`.
    """
    bare = value.split(".", 1)[-1]
    for module in MODULES:
        prefix = f"{module.key}_"
        if bare.startswith(prefix):
            action = bare[len(prefix):]
            if action in module.actions:
                return module.key, action
    return None


def catalogue_filter() -> dict[str, str]:
    """Keyword arguments narrowing a Permission queryset to the catalogue."""
    return {"content_type__app_label": APP_LABEL,
            "content_type__model": CONTENT_TYPE_MODEL}


def all_codenames() -> list[str]:
    return [codename(module.key, action)
            for module in MODULES for action in module.actions]


def all_permission_strings() -> list[str]:
    return [f"{APP_LABEL}.{name}" for name in all_codenames()]


def label_for(module_key: str, action: str) -> str:
    module = MODULES_BY_KEY.get(module_key)
    module_label = module.label if module else module_key
    return f"{ACTION_LABELS.get(action, action.title())} {module_label.lower()}"


def is_client_scoped(value: str) -> bool:
    """Whether a permission is limited to the staff member's assigned clients.

    Unknown permissions are treated as client-scoped: the safer answer is
    the one that restricts.
    """
    parts = split_codename(value)
    if parts is None:
        return True
    module = MODULES_BY_KEY.get(parts[0])
    return module.client_scoped if module else True
