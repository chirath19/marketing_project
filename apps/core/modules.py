"""The client portal's modules, and what each one requires.

One registry, shared by the domains that must not import each other: the
catalogue declares which module a service category unlocks, subscriptions
decide which a given client has earned, and the portal renders the
navigation and guards the routes from the same list.

It lives in `core` because that is the only place all of them may import
from. It is a closed list rather than free text: a module is a page
somebody has to build, so inventing one by typing a new string into the
admin would unlock a screen that does not exist.

**This is what "do not build a dashboard per client" means in practice.**
There is one portal. What a client sees in it is a function of their
active services, computed from this table — not of code written for them.

`access` is the whole point of the file:

* ``always``      — account-level. Every client has it, including one who
                    has bought nothing yet.
* ``any_service`` — needs at least one active service. There is nothing
                    to put on a campaigns page for somebody who is not a
                    client yet, and an empty page is worse than no link.
* ``service``     — needs an active service in a category mapped to this
                    module. This is the entitlement the brief is about.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ALWAYS = "always"
ANY_SERVICE = "any_service"
SERVICE = "service"


@dataclass(frozen=True, slots=True)
class PortalModule:
    key: str
    label: str
    #: What the client is told the area contains.
    description: str
    access: str = SERVICE
    #: Whether this module shows real data yet. False still unlocks the
    #: area and still says what it will hold — it simply has nothing to
    #: show, and says so rather than inventing some.
    #:
    #: Deliberately **not** the same question as `url_name`: Campaigns
    #: shows real records through the shared area route and has no page
    #: of its own, so the two would have disagreed.
    built: bool = False
    #: Route name, for the modules that have a dedicated page rather than
    #: rendering through `organizations:portal_module`.
    url_name: str = ""
    #: The areas this module will contain once built. Declared so the
    #: page can say what is coming instead of apologising.
    will_show: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PortalGroup:
    label: str
    modules: tuple[PortalModule, ...]


PORTAL_NAVIGATION: tuple[PortalGroup, ...] = (
    PortalGroup(
        "Your account",
        (
            PortalModule(
                "overview",
                "Overview",
                "What needs your attention, and what is running.",
                access=ALWAYS,
                built=True,
                url_name="organizations:overview",
            ),
            PortalModule(
                "services",
                "Services",
                "What we are delivering for you, and what each one opens up.",
                access=ALWAYS,
                built=True,
                url_name="organizations:services",
            ),
            PortalModule(
                "quotes",
                "Quotes",
                "Requests you have sent us, and where each one has got to.",
                access=ALWAYS,
                built=True,
                url_name="organizations:quotes",
            ),
        ),
    ),
    PortalGroup(
        "Delivery",
        (
            PortalModule(
                "campaigns",
                "Campaigns",
                "Everything running under your services: planned, live, paused or finished.",
                access=ANY_SERVICE,
                built=True,
                will_show=(
                    "Campaigns by state, across every service",
                    "What each one is trying to achieve",
                    "Start and end dates against the plan",
                    "Recent changes, and who made them",
                ),
            ),
            PortalModule(
                "seo",
                "Search",
                "Rankings, technical health, the content published for you and "
                "the work queued next.",
                will_show=(
                    "Positions for the terms that matter to you",
                    "Technical health and outstanding fixes",
                    "Content published and planned",
                    "Backlink activity",
                ),
            ),
            PortalModule(
                "paid_ads",
                "Paid advertising",
                "Spend, leads and cost per customer across every platform we run for you.",
                built=True,
                will_show=(
                    "Spend against budget",
                    "Leads, conversions and cost per customer",
                    "Performance by platform",
                    "What changed, and why",
                ),
            ),
            PortalModule(
                "social",
                "Social media",
                "Your content schedule, what has published, and anything waiting on your approval.",
                built=True,
                will_show=(
                    "The month's content calendar",
                    "Published posts and short-form video",
                    "Engagement and audience growth",
                    "Creator partnerships",
                ),
            ),
            PortalModule(
                "email_marketing",
                "Email marketing",
                "Campaigns and flows built for your audience, and how they performed.",
                built=True,
                will_show=(
                    "Campaigns sent, and what they returned",
                    "Automated flows and their performance",
                    "List health and segmentation",
                    "What is scheduled next",
                ),
            ),
            PortalModule(
                "analytics",
                "Analytics",
                "Performance across every active service, with the definitions behind each number.",
                will_show=(
                    "Results across every service in one view",
                    "Comparison against the previous period",
                    "Conversion tracking health",
                    "What each metric actually counts",
                ),
            ),
            PortalModule(
                "strategy",
                "Strategy",
                "Plans, channel decisions and quarterly performance reviews.",
                will_show=(
                    "The current plan and its targets",
                    "Channel and budget decisions",
                    "Quarterly performance reviews",
                ),
            ),
        ),
    ),
    PortalGroup(
        "Working together",
        (
            PortalModule(
                "reports",
                "Reports",
                "Published reporting on the work we are doing for you.",
                access=ALWAYS,
                built=True,
                url_name="organizations:client_reports",
                will_show=(
                    "Reports as they are published",
                    "The period each one covers",
                    "Downloads, where a report has a file",
                ),
            ),
            PortalModule(
                "approvals",
                "Approvals",
                "Anything that needs your decision before work continues.",
                access=ANY_SERVICE,
                built=True,
                will_show=(
                    "Items waiting on you",
                    "What you have approved, rejected or sent back",
                    "Who decided, and when",
                ),
            ),
            PortalModule(
                "messages",
                "Messages",
                "Conversations with your account team, kept with the work they are about.",
                # Always: somebody with no services yet still needs to reach
                # their account team, and that is exactly when they most need
                # to.
                access=ALWAYS,
                built=True,
                url_name="organizations:client_desk",
                will_show=(
                    "Conversations with your account team",
                    "Messages kept beside the work they concern",
                    "Nothing emailed — it all stays here",
                ),
            ),
        ),
    ),
    PortalGroup(
        "Organisation",
        (
            PortalModule(
                "invoices",
                "Invoices",
                "Invoices, balances and payment history.",
                access=ALWAYS,
                built=True,
                url_name="organizations:client_invoices",
            ),
            PortalModule(
                "service_requests",
                "Service requests",
                "Renewals, extensions and additional work.",
                access=ALWAYS,
                built=True,
                url_name="organizations:service_requests",
            ),
            PortalModule(
                "receipts",
                "Payment receipts",
                "Payment acknowledgements from your team.",
                access=ALWAYS,
                built=True,
                url_name="organizations:client_receipts",
            ),
            PortalModule(
                "people",
                "People",
                "Who from your company can see this workspace.",
                access=ALWAYS,
                built=True,
                url_name="organizations:members",
            ),
            PortalModule(
                "settings",
                "Settings",
                "Your company details.",
                access=ALWAYS,
                built=True,
                url_name="organizations:settings",
            ),
        ),
    ),
)


PORTAL_MODULES: tuple[PortalModule, ...] = tuple(
    module for group in PORTAL_NAVIGATION for module in group.modules
)

PORTAL_MODULES_BY_KEY: dict[str, PortalModule] = {module.key: module for module in PORTAL_MODULES}

#: Modules a service category can unlock. Only the service-gated ones:
#: offering "Overview" as something a category unlocks would be
#: meaningless, since every client has it already.
SERVICE_MODULES: tuple[PortalModule, ...] = tuple(
    module for module in PORTAL_MODULES if module.access == SERVICE
)

#: For `ServiceCategory.workspace_module`. The empty option is first and
#: means "unlocks nothing", which is the right default — a service can be
#: sold without a dashboard behind it.
MODULE_CHOICES = [("", "No workspace module")] + [
    (module.key, module.label) for module in SERVICE_MODULES
]


def get_module(key: str) -> PortalModule | None:
    return PORTAL_MODULES_BY_KEY.get(key or "")


def modules_for(keys) -> list[PortalModule]:  # noqa: ANN001
    """The service-gated modules named by `keys`, in registry order.

    Ordered here rather than by whatever order the subscriptions came
    back in, so a client's portal does not rearrange itself when they
    buy something new.
    """
    wanted = set(keys)
    return [module for module in SERVICE_MODULES if module.key in wanted]


def available_modules(*, service_keys, has_any_service: bool) -> list[PortalModule]:
    """Every module this client may open.

    The single answer to "what is this client entitled to", used by the
    navigation **and** by the route guard. They read the same function on
    purpose: a menu that hides a link while the view still serves it is
    not access control, it is decoration.
    """
    wanted = set(service_keys)

    #: One predicate per access rule, so the table reads as the rule it
    #: encodes. Collapsing these into a single boolean expression makes
    #: it shorter and considerably harder to check.
    unlocked_by = {
        ALWAYS: lambda module: True,
        ANY_SERVICE: lambda module: has_any_service,
        SERVICE: lambda module: module.key in wanted,
    }

    return [
        module
        for module in PORTAL_MODULES
        if unlocked_by.get(module.access, lambda module: False)(module)
    ]


def navigation_for(allowed) -> list[dict]:  # noqa: ANN001
    """The allowed modules, grouped for rendering.

    Groups with nothing visible in them are dropped, so a client with no
    services does not get an empty "Delivery" heading.
    """
    keys = {module.key for module in allowed}
    groups = []

    for group in PORTAL_NAVIGATION:
        modules = [module for module in group.modules if module.key in keys]
        if modules:
            groups.append({"label": group.label, "modules": modules})

    return groups
