"""The extension point service modules build on.

The brief's requirement, in one sentence: *service-specific modules
extend this core system instead of creating unrelated architectures.*

So there is **one** `Campaign` table. SEO, paid advertising, social and
email do not get a campaign model each — they register a type here and,
where they need fields of their own, attach a detail record to the
campaign rather than replacing it.

That buys the thing the supplied dashboard actually shows: one list,
across every service, with one set of statuses, one permission model and
one isolation rule. Four parallel campaign models would have meant four
of each, and a combined view assembled from four queries that agree about
nothing.

Registering a type is a declaration, not a subclass:

    register(CampaignType(
        key="seo",
        label="Search",
        goal_label="Target positions",
        detail_model="apps.seo.models.SeoCampaignDetail",
    ))

The `key` is deliberately the same vocabulary as
`apps.core.modules` — a campaign of type `seo` belongs in the client's
Search area, and nothing has to map between the two.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CampaignType:
    #: Matches a service-gated key in `apps.core.modules`, so a campaign
    #: lands in the portal area its service opened.
    key: str
    label: str
    #: What "what is this campaign trying to achieve" means for this
    #: type. "Target positions" reads very differently from "Return on
    #: ad spend", and a single generic label serves neither.
    goal_label: str = "Objective"
    #: Dotted path to a `CampaignDetail` subclass, where the type needs
    #: fields the core does not have. Resolved lazily so this module
    #: stays importable before the app registry is ready.
    detail_model: str = ""
    #: Dotted path to the `ModelForm` staff use to edit `detail_model`'s
    #: own fields — e.g. a paid campaign's platform and objective. A
    #: type with a detail model but no form here is read-only in the
    #: admin UI, which is a real gap worth noticing rather than a
    #: silent fallback.
    detail_form: str = ""
    description: str = ""


_TYPES: dict[str, CampaignType] = {}


def register(campaign_type: CampaignType) -> CampaignType:
    """Declare a campaign type.

    Idempotent by key, because modules are imported more than once in a
    test run and a duplicate registration is not an error worth
    crashing over.
    """
    _TYPES[campaign_type.key] = campaign_type
    return campaign_type


def get_type(key: str) -> CampaignType | None:
    return _TYPES.get(key or "")


def all_types() -> list[CampaignType]:
    """Registered types, in the order the portal lists their modules.

    Ordered by the shared module registry rather than by registration
    order, so the campaign filters and the client's sidebar agree about
    what comes first.
    """
    from apps.core.modules import SERVICE_MODULES

    order = {module.key: index for index, module in enumerate(SERVICE_MODULES)}
    return sorted(_TYPES.values(), key=lambda t: order.get(t.key, 99))


def type_choices() -> list[tuple[str, str]]:
    return [(campaign_type.key, campaign_type.label)
            for campaign_type in all_types()]


def detail_model_for(key: str):  # noqa: ANN201
    """The detail model a type attaches, or None.

    Resolved through Django's app registry rather than imported, so a
    service module can declare its detail model without this one
    importing it — which is what keeps the dependency pointing the right
    way.
    """
    campaign_type = get_type(key)
    if campaign_type is None or not campaign_type.detail_model:
        return None

    from django.apps import apps as django_apps

    module_path, _, class_name = campaign_type.detail_model.rpartition(".")
    app_label = module_path.split(".")[-2]
    try:
        return django_apps.get_model(app_label, class_name)
    except LookupError:  # pragma: no cover - a typo in a registration
        return None


def detail_form_for(key: str):  # noqa: ANN201
    """The `ModelForm` staff use to edit a type's detail fields, or None.

    A form class is not a Django model, so it cannot be resolved through
    the app registry the way `detail_model_for` is — this imports the
    dotted path directly instead. That still keeps the dependency
    pointing the right way: the campaign admin page asks this module for
    a form, it never imports `apps.paid_ads` or `apps.seo` by name.
    """
    campaign_type = get_type(key)
    if campaign_type is None or not campaign_type.detail_form:
        return None

    from django.utils.module_loading import import_string

    try:
        return import_string(campaign_type.detail_form)
    except ImportError:  # pragma: no cover - a typo in a registration
        return None


# ---------------------------------------------------------------------------
# The types the platform ships with
#
# Declared here, not in each service app, for one reason: those apps have
# no models yet. When `apps/seo` grows a detail model it moves its own
# registration into its `AppConfig.ready()`, and nothing else changes.
# ---------------------------------------------------------------------------

register(CampaignType(
    key="seo", label="Search", goal_label="Target positions",
    description="Technical work, content and links against the terms that "
                "bring customers.",
))
register(CampaignType(
    key="paid_ads", label="Paid advertising", goal_label="Cost per customer",
    description="Campaigns on Google, Meta and LinkedIn, run against a "
                "budget.",
))
register(CampaignType(
    key="social", label="Social media", goal_label="Reach and engagement",
    description="Publishing, community management and creator work.",
))
register(CampaignType(
    key="email_marketing", label="Email marketing", goal_label="Revenue per send",
    description="Campaigns and automated flows for the client's own list.",
))
register(CampaignType(
    key="analytics", label="Analytics", goal_label="What it must measure",
    description="Tracking, measurement and reporting work.",
))
register(CampaignType(
    key="strategy", label="Strategy", goal_label="The decision it informs",
    description="Planning, channel selection and performance review.",
))
