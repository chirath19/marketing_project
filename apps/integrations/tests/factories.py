"""Test helpers for the Integrations domain."""

from __future__ import annotations

__all__ = ["make_connection"]


def make_connection(*, provider: str = "meta_ads", organization=None, actor=None,  # noqa: ANN001
                    **fields):  # noqa: ANN201
    """A connection, built the way the real one is."""
    from apps.integrations.services import create_connection
    from apps.staff.tests.factories import make_super_admin_user

    return create_connection(
        provider=provider, organization=organization,
        actor=actor or make_super_admin_user("integrations-setup@heliograph.agency"),
        **fields,
    )
