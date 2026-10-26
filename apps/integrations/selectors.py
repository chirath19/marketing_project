"""Read access for the Integrations domain.

Every queryset here is already scoped. Nothing outside this module and
`apps.integrations.providers` should import `IntegrationConnection`
directly — reading through here is what keeps a secret field from being
added to a template context by accident, because every function returning
a connection returns the model instance, and the model's own properties
(`masked_account_id`, `is_configured`) are the only safe way anything
downstream touches it.
"""

from __future__ import annotations

from django.db.models import Count, QuerySet

from apps.integrations import policies
from apps.integrations.models import (
    AnalyticsSyncRun,
    ExternalCampaignReference,
    IntegrationConnection,
    Provider,
)


def visible_connections(
    actor,
    *,
    provider: str = "",  # noqa: ANN001
    organization=None,
) -> QuerySet:
    if not policies.can_view_integrations(actor):
        return IntegrationConnection.objects.none()

    from apps.permissions.guards import scope_to_accessible

    queryset = IntegrationConnection.objects.select_related("organization", "created_by")
    # Agency-wide rows (organization is NULL) are never scoped away —
    # `scope_to_accessible` only narrows rows that have an organization.
    queryset = scope_to_accessible(queryset, actor, field="organization_id")

    from apps.core.features import visible

    if not actor.is_super_admin:
        queryset = queryset.filter(
            provider__in=[key for key in Provider.values if visible(key, actor)]
        )
    if provider:
        queryset = queryset.filter(provider=provider)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return queryset


def get_connection(actor, pk: int):  # noqa: ANN001, ANN201
    connection = IntegrationConnection.objects.select_related("organization").filter(pk=pk).first()
    from apps.core.features import visible

    if (
        connection is None
        or not visible(connection.provider, actor)
        or not policies.can_view_connection(actor, connection)
    ):
        return None
    return connection


def connection_for(organization, provider: str):  # noqa: ANN201
    """The one connection a client has for a provider, if any.

    `None` is a legitimate, common answer — most clients have no
    integration connection at all, and every caller must treat that as
    "show the empty state" rather than an error.
    """
    return IntegrationConnection.objects.filter(
        organization=organization,
        provider=provider,
    ).first()


def provider_overview(actor) -> list[dict]:  # noqa: ANN001
    """One row per provider, for the Integrations admin page.

    Counts connections by status so the page can say "3 connected, 1
    needs reauthorization" without the template looping twice.
    """
    if not policies.can_view_integrations(actor):
        return []

    connections = IntegrationConnection.objects.values("provider", "status").annotate(
        total=Count("pk")
    )
    by_provider: dict[str, dict[str, int]] = {}
    for row in connections:
        by_provider.setdefault(row["provider"], {})[row["status"]] = row["total"]

    from apps.core.features import visible
    from apps.integrations.providers import get_adapter

    return [
        {
            "provider": value,
            "label": label,
            "has_adapter": get_adapter(value) is not None,
            "counts": by_provider.get(value, {}),
            "total_connections": sum(by_provider.get(value, {}).values()),
        }
        for value, label in Provider.choices
        if visible(value, actor)
    ]


def sync_history(
    actor,
    *,
    provider: str = "",
    organization=None,  # noqa: ANN001
    limit: int = 50,
) -> QuerySet:
    if not policies.can_view_integrations(actor):
        return AnalyticsSyncRun.objects.none()

    queryset = AnalyticsSyncRun.objects.select_related("connection", "organization", "triggered_by")
    from apps.core.features import visible

    if not actor.is_super_admin:
        queryset = queryset.filter(
            provider__in=[key for key in Provider.values if visible(key, actor)]
        )
    if provider:
        queryset = queryset.filter(provider=provider)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return queryset[:limit]


def last_sync_for(organization, provider: str):  # noqa: ANN201
    """The most recent sync attempt, for a "Last updated" indicator."""
    return (
        AnalyticsSyncRun.objects.filter(organization=organization, provider=provider)
        .order_by("-started_at")
        .first()
    )


def mappings_for_campaign(actor, campaign) -> QuerySet:  # noqa: ANN001
    """External references for one campaign, scoped by the same rule as
    the campaign itself — a mapping is only as private as its campaign."""
    from apps.campaigns import policies as campaign_policies

    if not campaign_policies.can_view_campaigns(actor, campaign.organization):
        return ExternalCampaignReference.objects.none()

    return ExternalCampaignReference.objects.filter(campaign=campaign).select_related("connection")


def credential_status(actor, provider: str) -> list[dict]:
    """Whether each app-level credential field is set, for the provider
    page — never the value itself, only a yes/no and where it came
    from. Returns `[]` if the actor may not see this at all."""
    if not policies.can_view_integrations(actor):
        return []

    from apps.integrations.credentials import fields_for, get
    from apps.integrations.models import ProviderCredential

    stored_keys = set(
        ProviderCredential.objects.filter(provider=provider)
        .exclude(value="")
        .values_list("key", flat=True)
    )
    return [
        {
            "label": field.label,
            "configured": bool(get(provider, field.key)),
            "source": "dashboard" if field.key in stored_keys else "environment",
        }
        for field in fields_for(provider)
    ]
