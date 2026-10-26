"""`EncryptedTextField` — the column must never hold the plain value."""

from __future__ import annotations

import pytest
from django.db import connection

from apps.accounts.tests.factories import make_super_admin
from apps.integrations.models import IntegrationConnection, Provider

pytestmark = pytest.mark.django_db


def _raw_access_token(connection_id: int) -> str:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT access_token FROM integrations_integrationconnection WHERE id = %s",
            [connection_id],
        )
        return cursor.fetchone()[0]


def test_the_stored_column_is_ciphertext_not_plaintext():
    admin = make_super_admin()
    row = IntegrationConnection.objects.create(
        provider=Provider.META_ADS, external_account_id="act_999",
        access_token="super-secret-token-value", created_by=admin,
    )

    raw = _raw_access_token(row.pk)

    assert "super-secret-token-value" not in raw
    assert raw != ""


def test_the_orm_reads_back_the_plain_value():
    row = IntegrationConnection.objects.create(
        provider=Provider.META_ADS, external_account_id="act_999",
        access_token="super-secret-token-value",
    )

    fetched = IntegrationConnection.objects.get(pk=row.pk)

    assert fetched.access_token == "super-secret-token-value"


def test_a_blank_value_is_stored_blank_not_as_ciphertext():
    row = IntegrationConnection.objects.create(
        provider=Provider.META_ADS, external_account_id="act_999",
        access_token="",
    )

    assert _raw_access_token(row.pk) == ""
    assert IntegrationConnection.objects.get(pk=row.pk).access_token == ""


def test_an_unreadable_value_decrypts_to_blank_rather_than_raising(settings):
    """A token written under one `FIELD_ENCRYPTION_KEY` and read back
    under another (a rotated key, or a row from a different
    environment) must not crash the page that reads this connection —
    it has `needs_attention`/`is_configured` to notice instead."""
    row = IntegrationConnection.objects.create(
        provider=Provider.META_ADS, external_account_id="act_999",
        access_token="super-secret-token-value",
    )

    settings.FIELD_ENCRYPTION_KEY = "a-completely-different-key-entirely"

    fetched = IntegrationConnection.objects.get(pk=row.pk)

    assert fetched.access_token == ""
