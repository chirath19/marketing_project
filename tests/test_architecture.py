"""Guards on the modular monolith's structure.

These are the rules that are easy to state in a document and easy to
break in a hurry. Encoding them as tests is what makes them hold.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings

BASE_DIR = Path(settings.BASE_DIR)
APPS_DIR = BASE_DIR / "apps"

EXPECTED_DOMAINS = {
    "core",
    "accounts",
    "organizations",
    "staff",
    "permissions",
    "cms",
    "catalog",
    "leads",
    "subscriptions",
    "campaigns",
    "seo",
    "paid_ads",
    "social",
    "email_marketing",
    "analytics",
    "approvals",
    "messaging",
    "notifications",
    "media",
    "integrations",
    "audit",
    "tracking",
}


def app_dirs() -> list[Path]:
    return sorted(
        path for path in APPS_DIR.iterdir() if path.is_dir() and (path / "apps.py").exists()
    )


def test_every_planned_domain_exists():
    assert {path.name for path in app_dirs()} == EXPECTED_DOMAINS


def test_every_domain_is_installed():
    installed = set(settings.INSTALLED_APPS)

    for name in EXPECTED_DOMAINS:
        assert f"apps.{name}" in installed, f"apps.{name} is missing from INSTALLED_APPS"


def test_every_domain_declares_the_layering_modules():
    """Each domain exposes reads, writes and authorisation as separate
    modules. Keeping the files present is what makes putting logic in the
    right place the path of least resistance."""
    for path in app_dirs():
        for module in ("selectors.py", "services.py", "policies.py"):
            assert (path / module).exists(), f"{path.name} is missing {module}"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)

    return found


def presentation_modules() -> list[tuple[str, Path]]:
    """views.py, views/, api/ and serializers.py across every domain."""
    found: list[tuple[str, Path]] = []

    for app in app_dirs():
        for candidate in ("views.py", "serializers.py"):
            if (app / candidate).exists():
                found.append((app.name, app / candidate))
        for folder in ("views", "api"):
            if (app / folder).is_dir():
                found.extend((app.name, f) for f in (app / folder).rglob("*.py"))

    return found


@pytest.mark.parametrize(
    ("app_name", "path"),
    presentation_modules(),
    ids=lambda value: value.name if isinstance(value, Path) else str(value),
)
def test_presentation_layer_does_not_reach_into_another_domains_models(app_name, path):
    """A view may call another domain's selectors and services. Importing
    its models reaches past the contract and couples the two domains
    together — the thing the modular monolith exists to prevent."""
    offenders = [
        module
        for module in _imports(path)
        if module.startswith("apps.")
        and module.endswith(".models")
        and not module.startswith(f"apps.{app_name}.")
    ]

    assert not offenders, (
        f"{path.relative_to(BASE_DIR)} imports {offenders}. "
        "Use that domain's selectors or services instead."
    )


def test_no_domain_imports_another_domains_internals_from_its_models():
    """Models stay at the bottom of the stack: importing a service from a
    model is how business logic ends up back inside save()."""
    for app in app_dirs():
        models_file = app / "models.py"
        if not models_file.exists():
            continue

        offenders = [
            module
            for module in _imports(models_file)
            if module.startswith("apps.")
            and (module.endswith(".services") or module.endswith(".views"))
        ]

        assert not offenders, f"{models_file.relative_to(BASE_DIR)} imports {offenders}"


# ---------------------------------------------------------------------------
# Tenancy
#
# Everything the platform produces for a client belongs to an
# Organization, not to a user. These guards are what stop a later phase
# quietly attaching a campaign or a report to `request.user` instead.
# ---------------------------------------------------------------------------

#: Domains whose records belong to a client organization. As each is
#: built, its models must inherit OrganizationOwnedModel so they get the
#: isolation rule for free.
TENANT_DOMAINS = {
    "campaigns",
    "subscriptions",
    "approvals",
    "messaging",
    "analytics",
    "seo",
    "paid_ads",
    "social",
    "email_marketing",
    "leads",
}

#: Domains whose records genuinely do not belong to a client.
#:
#: `notifications` is per-person, not per-client: a notification is
#: addressed to a user and read by that user. Scoping it to an
#: organization would be meaningless for staff, who belong to none.
NON_TENANT_DOMAINS = {"notifications"}


def _concrete_models(app_label: str) -> list:
    from django.apps import apps as django_apps

    try:
        config = django_apps.get_app_config(app_label)
    except LookupError:  # pragma: no cover - the app list is fixed
        return []

    return [model for model in config.get_models() if not model._meta.abstract]


def _belongs_to_an_organization(model, *, depth: int = 2) -> bool:
    """Whether a model can be traced to a client organization.

    Three ways count, because all three are legitimate:

    * it inherits `OrganizationOwnedModel`;
    * it has a foreign key straight to `Organization` — which is what a
      lead has, nullable, because an enquiry predates any client
      relationship;
    * it relates to something that satisfies either of the above, which
      is how a lead's activity row or a campaign's metric row reaches an
      owner without being denormalised.
    """
    from apps.organizations.models import Organization, OrganizationOwnedModel

    if issubclass(model, OrganizationOwnedModel):
        return True

    for field in model._meta.get_fields():
        related = getattr(field, "related_model", None)
        if related is None:
            continue
        if related is Organization or issubclass(related, OrganizationOwnedModel):
            return True
        if (
            depth > 0
            and related is not model
            and _belongs_to_an_organization(related, depth=depth - 1)
        ):
            return True

    return False


@pytest.mark.parametrize("app_label", sorted(TENANT_DOMAINS))
def test_every_model_in_a_tenant_domain_belongs_to_an_organization(app_label):
    """A record in one of these domains without an organization has no
    owner, and no way to be isolated from other clients.

    Domains with no models yet pass trivially; the test starts biting the
    moment one is added.
    """
    offenders = [
        model.__name__
        for model in _concrete_models(app_label)
        if not _belongs_to_an_organization(model)
        # The agency-wide invoice/receipt counter stores only a namespace and
        # an integer, not client records. References must be unique across clients.
        and model._meta.label_lower != "subscriptions.billingsequence"
    ]

    assert not offenders, (
        f"{app_label}: {offenders} belong to no organization. Inherit "
        "OrganizationOwnedModel, add a foreign key to Organization, or "
        "relate to something that already does."
    )


@pytest.mark.parametrize("app_label", sorted(NON_TENANT_DOMAINS))
def test_a_non_tenant_domain_is_a_stated_exception(app_label):
    """Listing a domain here is a decision, not an omission.

    This asserts the exception is real — if one of these ever grows a
    client-owned model, it belongs in TENANT_DOMAINS instead.
    """
    assert _concrete_models(app_label), (
        f"{app_label} has no models; remove it from NON_TENANT_DOMAINS."
    )


def test_the_tenancy_base_is_the_only_implementation_of_the_isolation_rule():
    """`visible_to` exists in one place. A domain writing its own would be
    a second rule to keep in step — and the one that drifts."""
    from apps.organizations.models import OrganizationOwnedQuerySet

    source = (APPS_DIR / "organizations" / "models.py").read_text()
    assert "def visible_to" in source
    assert hasattr(OrganizationOwnedQuerySet, "visible_to")

    # Any other definition must be in organizations, which owns the rule.
    definitions = [
        path.relative_to(BASE_DIR)
        for path in APPS_DIR.rglob("*.py")
        if "def visible_to" in path.read_text()
    ]
    outside = [str(path) for path in definitions if not str(path).startswith("apps/organizations/")]

    assert not outside, f"visible_to is defined outside the organizations domain: {outside}"


# ---------------------------------------------------------------------------
# Authorisation
#
# A view that forgets its guard is the failure mode this phase exists to
# prevent, and it is invisible in review — the page simply works.
# ---------------------------------------------------------------------------

#: Views that are reachable without a platform permission, each for a
#: stated reason. Anything else in a guarded module must carry a guard.
UNGUARDED_VIEWS = {
    # Personal alerts use authentication and recipient-scoped selectors; clients
    # hold no platform permissions. Cross-user reads/writes are tested explicitly.
    "apps/notifications/views.py",
    # Direct recipient, active membership and selected organization enforced by the desk policy.
    "apps/messaging/views/client.py",
    # Selected organization, active services, source sharing and client membership role.
    "apps/approvals/views/client.py",
    # Selected organization, entitlement, sharing flags and client review role.
    "apps/social/views/client.py",
    # Selected organization, service entitlement, sharing and client review roles.
    "apps/email_marketing/views/client.py",
    # Selected-organization membership plus active Paid Ads entitlement; read-only.
    "apps/paid_ads/views/client.py",
    # Public site and error pages.
    "apps/core/views.py",
    # Sign in, register, profile: guarded by authentication, not by a
    # platform permission, and a client holds none of those.
    "apps/accounts/views.py",
    # A client's own organization: guarded by membership, which is a
    # different mechanism (see apps/organizations/middleware.py).
    "apps/organizations/views/workspace.py",
    # The client portal's delivery modules. A client holds no platform
    # permission, so there is none to require. These are guarded by
    # **entitlement** instead — `apps.subscriptions.guards` — which the
    # test below asserts, and which the sidebar is built from so the two
    # cannot disagree.
    "apps/organizations/views/portal.py",
    # The public marketing site. Open to the world on purpose — that is
    # what it is for. It only ever renders published CMS pages, and a
    # test asserts a draft is a 404 for everyone.
    "apps/cms/views/public.py",
    # The public blog, for the same reason. Published posts only — a
    # draft is a 404 for everyone, and a test asserts it.
    "apps/cms/views/blog.py",
    # The public service catalogue and the quote selection a visitor
    # builds. Open by design: it is the shop window. Only live services
    # are shown, the selection lives in the visitor's own session, and
    # the state-changing routes are POST-only.
    "apps/catalog/views/public.py",
    # The public contact and quote forms. Open by design — they are how
    # someone reaches the agency. Guarded instead by a honeypot, a signed
    # render timestamp, a rate limit and content heuristics.
    "apps/leads/views/public.py",
    # The agency website's event ingestion endpoint. Open by design — it
    # is called by every visitor's browser before any of them could sign
    # in. Guarded instead by a closed, server-checked event taxonomy
    # (only `events.CLIENT_REPORTABLE_EVENTS` is ever accepted) and a
    # rate limit; see apps/tracking/views.py.
    "apps/tracking/views.py",
    # A client's own quote requests. A client holds no platform
    # permission, so there is none to require: every view here resolves
    # the quote through `selectors.client_quote`, which applies the
    # ownership rule to the row itself and returns None otherwise. A
    # separate test drives these routes as the wrong client and asserts
    # a 404.
    "apps/leads/views/client.py",
    # A client's own services, for the same reason. Each view resolves
    # the record through `selectors.client_subscription`, which applies
    # the tenancy rule to the row; the isolation tests drive these routes
    # as the wrong client and assert a 404.
    "apps/subscriptions/views/client.py",
    # A client's own campaigns, likewise: resolved through
    # `selectors.client_campaign`, which applies the tenancy rule to the
    # row, and reached only through the portal's entitlement guard.
    "apps/campaigns/views/client.py",
}

GUARD_MARKERS = (
    "require_permission",
    "require_staff_member",
    "PermissionRequiredMixin",
    "ensure_can",
    "require_guest_quote",
    "require_client_module",
)


def _view_functions(path: Path) -> list[tuple[str, list[str]]]:
    """Public view callables in a module, with their decorator names."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue

        decorators = []
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            decorators.append(getattr(target, "id", None) or getattr(target, "attr", ""))
        found.append((node.name, decorators))

    return found


def view_modules() -> list[Path]:
    """Every module holding views, whether `views.py` or a `views/` package.

    Globbing for `views.py` alone missed a package entirely — the moment
    the staff views were split into `views/`, the guard below stopped
    checking any of them.
    """
    found = list(APPS_DIR.rglob("views.py"))
    for app in APPS_DIR.iterdir():
        package = app / "views"
        if package.is_dir():
            found.extend(path for path in package.rglob("*.py") if path.name != "__init__.py")
    return sorted(found)


def guarded_view_modules() -> list[Path]:
    return [
        path for path in view_modules() if str(path.relative_to(BASE_DIR)) not in UNGUARDED_VIEWS
    ]


@pytest.mark.parametrize("path", guarded_view_modules(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_view_in_a_guarded_module_declares_a_permission(path):
    """A view without `@require_permission` is open to any signed-in user.

    If a module genuinely has no permission-guarded views, add it to
    UNGUARDED_VIEWS with the reason — the point is that it is a decision,
    not an omission.
    """
    source = path.read_text()
    offenders = [
        name
        for name, decorators in _view_functions(path)
        if not any(marker in decorators for marker in GUARD_MARKERS)
        and not any(
            f"{marker}(" in source.split(f"def {name}")[0][-400:] for marker in GUARD_MARKERS
        )
    ]

    assert not offenders, f"{path.relative_to(BASE_DIR)}: {offenders} carry no permission guard."


def test_the_api_permission_class_is_not_bypassed():
    """A DRF viewset without `permission_classes` falls back to the
    project default, which is only `IsAuthenticated` — enough to let any
    signed-in client read staff data."""
    api_modules = sorted(APPS_DIR.rglob("api.py"))

    for path in api_modules:
        source = path.read_text()
        if "ViewSet" not in source and "APIView" not in source:
            continue
        assert "permission_classes" in source, (
            f"{path.relative_to(BASE_DIR)} defines an API view with no permission_classes."
        )


def test_the_guards_are_defined_only_in_the_permissions_domain():
    """One implementation of the rule, as with tenant isolation."""
    definitions = [
        path.relative_to(BASE_DIR)
        for path in APPS_DIR.rglob("*.py")
        if "def require_permission" in path.read_text()
    ]

    assert [str(path) for path in definitions] == ["apps/permissions/guards.py"]


def test_the_view_guard_actually_covers_the_staff_package():
    """A guard that silently inspects nothing passes forever.

    The staff views live in a package; this asserts they are in the set
    the test above walks, so splitting a module cannot switch the check
    off by accident.
    """
    covered = {str(path.relative_to(BASE_DIR)) for path in guarded_view_modules()}

    assert "apps/staff/views/modules.py" in covered
    assert "apps/staff/views/clients.py" in covered
    assert "apps/staff/views/dashboard.py" in covered


def test_every_navigation_item_points_at_a_guarded_route():
    """A menu item leading to an unguarded page would be worse than no
    menu item at all."""
    from django.urls import reverse

    from apps.staff.navigation import NAVIGATION

    for group in NAVIGATION:
        for item in group.items:
            # Resolving proves the route exists; the guard test above
            # proves its view carries a permission decorator.
            assert reverse(item.url_name), item.key


def test_every_navigation_permission_exists_in_the_catalogue():
    """A menu item naming a permission nobody can hold would be invisible
    to everyone, including the person who should see it."""
    from apps.permissions.catalogue import all_codenames
    from apps.staff.navigation import NAVIGATION

    known = set(all_codenames())
    for group in NAVIGATION:
        for item in group.items:
            if item.permission:
                assert item.permission in known, (
                    f"{item.key} requires {item.permission!r}, which the "
                    "catalogue does not declare."
                )


def test_billing_counter_exception_contains_no_client_records():
    from apps.subscriptions.models import BillingSequence

    assert {field.name for field in BillingSequence._meta.fields} == {"id", "key", "value"}
    assert not _belongs_to_an_organization(BillingSequence)
