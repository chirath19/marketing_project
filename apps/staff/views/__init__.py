"""Staff dashboard views.

A package rather than one module: twenty-three navigation sections in a
single file would be unreadable. `urls.py` imports from here.
"""

from apps.staff.views.clients import (
    client_detail,
    client_list,
    export_client,
    export_clients,
)
from apps.staff.views.dashboard import dashboard, search
from apps.staff.views.roles import role_detail, role_list, role_set_permissions
from apps.staff.views.staff_admin import (
    assign_client,
    end_client_assignment,
    staff_create,
    staff_detail,
    staff_list,
    staff_set_active,
    staff_set_roles,
    staff_update,
)

__all__ = [
    "assign_client", "client_detail", "client_list", "dashboard",
    "end_client_assignment", "export_client", "export_clients",
    "role_detail", "role_list", "role_set_permissions", "search",
    "staff_create", "staff_detail", "staff_list", "staff_set_active",
    "staff_set_roles", "staff_update",
]
