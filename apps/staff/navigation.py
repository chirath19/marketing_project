"""The admin dashboard's navigation.

Declared once, here. Every item names the permission it requires, and the
menu is filtered server-side by the same `access.can()` that guards the
view behind it — so a menu item and its page can never disagree.

The filtering is presentation, not protection. Each view carries its own
`@require_permission` as well; a test asserts that every item in this
registry points at a guarded route. Hiding a link has never stopped
anyone typing the URL.

`built` marks whether the section's module exists yet. Sections that do
not are still listed, still permission-checked and still reachable — they
render an honest "not built yet" page rather than inventing data.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NavItem:
    key: str
    label: str
    url_name: str
    permission: str
    #: Whether the feature behind this item exists. False renders the
    #: placeholder page.
    built: bool = False
    #: The phase that will build it — shown on the placeholder so the page
    #: says something true rather than "coming soon".
    phase: str = ""
    description: str = ""
    #: The areas this section will hold once its module is built.
    #: Declared here so the placeholder page can say what is coming
    #: instead of apologising — and so the intended shape of a module is
    #: recorded somewhere a reader will actually find it. Empty for a
    #: section that already exists.
    will_show: tuple[str, ...] = ()

    @property
    def is_module_placeholder(self) -> bool:
        return not self.built


@dataclass(frozen=True, slots=True)
class NavGroup:
    label: str
    items: tuple[NavItem, ...] = field(default_factory=tuple)


NAVIGATION: tuple[NavGroup, ...] = (
    NavGroup(
        "Overview",
        (
            NavItem(
                "dashboard",
                "Dashboard",
                "staff:dashboard",
                "",
                built=True,
                description="What needs your attention.",
            ),
        ),
    ),
    NavGroup(
        "Clients",
        (
            NavItem(
                "service_requests",
                "Service requests",
                "staff:service_requests",
                "subscriptions_view",
                built=True,
            ),
            NavItem(
                "clients",
                "Clients",
                "staff:clients",
                "organizations_view",
                built=True,
                description="The organizations you are assigned to.",
            ),
            NavItem(
                "leads",
                "Leads",
                "staff:module_leads",
                "leads_view",
                built=True,
                description="The pipeline, from first enquiry on.",
            ),
            NavItem(
                "quotes",
                "Quote requests",
                "staff:module_quotes",
                "quotes_view",
                built=True,
                description="The quote pipeline, from request to decision.",
            ),
            NavItem(
                "subscriptions",
                "Client services",
                "staff:module_subscriptions",
                "subscriptions_view",
                built=True,
                description="What each client is paying for, and what that "
                "opens in their workspace.",
            ),
            NavItem(
                "approvals",
                "Approvals",
                "staff:module_approvals",
                "approvals_view",
                built=True,
                description="Work waiting on a client decision.",
                will_show=(
                    "Items pending a client decision",
                    "Approved, rejected and changes requested",
                    "Who decided, and when",
                    "Cancelled requests, kept for the record",
                ),
            ),
        ),
    ),
    NavGroup(
        "Delivery",
        (
            NavItem(
                "campaigns",
                "Campaigns",
                "staff:module_campaigns",
                "campaigns_view",
                built=True,
                description="Everything running across every service, for "
                "every client you work with.",
            ),
            NavItem(
                "seo",
                "SEO",
                "staff:module_seo",
                "seo_view",
                built=True,
                description="Audits, keywords, work and links — per client.",
            ),
            NavItem(
                "paid_ads",
                "Paid ads",
                "staff:module_paid_ads",
                "paid_ads_view",
                built=True,
                description="Advertising performance across platforms.",
                will_show=(
                    "Spend, leads and conversions",
                    "Cost per lead and return on ad spend",
                    "Clicks, impressions, click-through rate and cost per click",
                    "Performance by platform",
                    "Progress against the monthly goal",
                ),
            ),
            NavItem(
                "social",
                "Social media",
                "staff:module_social",
                "social_view",
                built=True,
                description="Publishing, community and creator work.",
                will_show=(
                    "The content schedule and what has published",
                    "Posts and short-form video",
                    "Creator partnerships and their deliverables",
                    "Engagement and audience growth",
                    "Items waiting on client approval",
                ),
            ),
            NavItem(
                "email_marketing",
                "Email marketing",
                "staff:module_email_marketing",
                "email_marketing_view",
                built=True,
                description="Marketing work done for clients. The platform "
                "still sends nothing itself.",
                will_show=(
                    "Campaigns planned and delivered for clients",
                    "Newsletter projects",
                    "Automation flows being built",
                    "Performance reported back from the client's own sending platform",
                    "Deliverables awaiting approval",
                ),
            ),
            NavItem(
                "analytics",
                "Analytics",
                "staff:module_analytics",
                "analytics_view",
                phase="Measurement",
                description="Measurement and reporting across services.",
                will_show=(
                    "Performance across every active service",
                    "Date range comparison",
                    "Conversion tracking health",
                    "Published reports",
                    "Definitions for each metric, so a figure cannot be read two ways",
                ),
            ),
        ),
    ),
    NavGroup(
        "Communication",
        (
            NavItem("messages", "Client workspace", "staff:module_messages", "", built=True),
            # Guarded by `leads_view`, not `messaging_view`: this is the
            # enquiry inbox. Client message threads are a separate surface.
            NavItem(
                "inbox",
                "Inbox",
                "staff:module_inbox",
                "leads_view",
                built=True,
                description="Where every enquiry and quote request lands.",
            ),
            # No permission: notifications are personal, and every staff
            # member sees their own. The route is staff-guarded instead.
            NavItem(
                "notifications",
                "Notifications",
                "staff:module_notifications",
                "",
                built=True,
                description="What needs your attention.",
            ),
        ),
    ),
    NavGroup(
        "Content",
        (
            NavItem(
                "services",
                "Services",
                "staff:module_services",
                "catalog_view",
                built=True,
                description="The service catalogue.",
            ),
            NavItem(
                "cms",
                "Website content",
                "staff:module_cms",
                "cms_view",
                built=True,
                description="Pages, sections and the lists they draw on.",
            ),
            NavItem(
                "blog",
                "Blog",
                "staff:module_blog",
                "blog_view",
                built=True,
                description="Posts, categories and tags.",
            ),
            NavItem(
                "media",
                "Media",
                "staff:module_media",
                "media_view",
                phase="CMS",
                description="Images and files used across the site.",
                will_show=(
                    "Everything uploaded, in one library",
                    "Where each file is used",
                    "Image descriptions for accessibility",
                    "Replace a file without breaking its links",
                ),
            ),
        ),
    ),
    NavGroup(
        "Administration",
        (
            NavItem(
                "staff",
                "Staff",
                "staff:list",
                "staff_view",
                built=True,
                description="Who works here and what they can do.",
            ),
            NavItem("roles", "Roles and permissions", "staff:roles", "roles_view", built=True),
            NavItem(
                "integrations",
                "Integrations",
                "staff:module_integrations",
                "integrations_view",
                built=True,
                description="External accounts the agency can pull "
                "analytics from, and when each last synced.",
            ),
            NavItem(
                "audit",
                "Audit logs",
                "staff:module_audit",
                "audit_view",
                phase="Audit",
                description="A record of who changed what.",
                will_show=(
                    "Every significant change, with the actor",
                    "Permission and role changes",
                    "Client record access",
                    "Filter by person, client or date",
                ),
            ),
            NavItem(
                "settings",
                "Settings",
                "staff:module_settings",
                "settings_manage",
                built=True,
                description="Platform-wide configuration.",
                will_show=(
                    "Registration and approval behaviour",
                    "Defaults for new clients",
                    "Currency and regional settings",
                    "Data retention",
                ),
            ),
        ),
    ),
)


ALL_ITEMS: dict[str, NavItem] = {item.key: item for group in NAVIGATION for item in group.items}


def visible_navigation(user) -> list[dict]:  # noqa: ANN001
    """The navigation this actor may see.

    Groups with nothing visible in them are dropped, so a specialist does
    not get an empty "Administration" heading.
    """
    from apps.permissions import access
    from apps.permissions.catalogue import APP_LABEL

    if user is None or not getattr(user, "is_authenticated", False):
        return []
    if not user.is_staff_member:
        return []

    from apps.core.features import FEATURES, settings_for, visible

    operating = settings_for(user)
    groups = []
    for group in NAVIGATION:
        items = [
            item
            for item in group.items
            if not item.permission or access.has_permission(user, f"{APP_LABEL}.{item.permission}")
        ]
        items = [
            item
            for item in items
            if (visible("client_workspace", user, operating=operating)
                if item.key == "messages" else
                item.key not in FEATURES or visible(item.key, user, operating=operating))
        ]
        if items:
            groups.append({"label": group.label, "items": items})

    return groups


def item_for(key: str) -> NavItem | None:
    return ALL_ITEMS.get(key)
