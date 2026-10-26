"""Client-facing views for an organization.

Split into two modules for a reason worth stating: `workspace.py` is
about the organization as a record — its details, its people, switching
between them — and `portal.py` is the dashboard assembled from what the
client has bought. The first is guarded by membership, the second by
membership *and* entitlement.

Re-exported here so `from apps.organizations import views` keeps working
and the URL conf does not have to know about the split.
"""

from apps.organizations.views.portal import (  # noqa: F401
    module_page,
)
from apps.organizations.views.workspace import (  # noqa: F401
    change_member_role,
    members,
    overview,
    remove_member,
    settings_view,
    setup,
    switch,
)
