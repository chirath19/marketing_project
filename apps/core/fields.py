"""Field-level encryption for secrets that must live in a database row.

`apps.integrations.IntegrationConnection` has no choice but to store a
provider's access token, refresh token and client secret somewhere —
syncing tomorrow needs them today. The brief is explicit that these must
never reach a template, a serializer or a log line in the clear (see
`apps/integrations/models.py`'s own docstring), but that is a read-side
discipline; it says nothing about the column itself. This field is the
write-side half: the value is encrypted before it reaches PostgreSQL, so
a database dump, a backup, or a stray `SELECT *` in a support session
never hands over a usable token either.

The key comes from `settings.FIELD_ENCRYPTION_KEY`, which must be set
from the environment in any deployment that holds a real secret — see
`.env.example`. A development environment that never configures a real
provider gets a key derived from `SECRET_KEY` instead, so `manage.py
check` and the test suite do not need their own key management; that
derived key is not a substitute for a real one anywhere tokens are real.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not key:
        # Derived, not random: every process in this environment must
        # decrypt what another process in the same environment wrote.
        # Deliberately not used for anything that holds a real secret —
        # see the module docstring.
        key = settings.SECRET_KEY
    digest = hashlib.sha256(key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class EncryptedTextField(models.TextField):
    """A `TextField` whose value is encrypted at rest with Fernet.

    Transparent to every caller: `connection.access_token = "..."` and
    `connection.access_token` read back the plain value, exactly like an
    ordinary field. Only the bytes PostgreSQL actually stores are
    ciphertext. Blank values are stored as-is rather than encrypted —
    there is nothing to protect in an empty string, and encrypting it
    would turn "not set" into a value that has to be decrypted to tell.
    """

    def get_prep_value(self, value):  # noqa: ANN001, ANN201
        value = super().get_prep_value(value)
        if not value:
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):  # noqa: ANN001, ANN201, ARG002
        if not value:
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            # A value written before FIELD_ENCRYPTION_KEY was rotated, or
            # under a different key entirely. Treated as unreadable
            # rather than raising into every page that touches this
            # connection — the caller already has `is_configured` and
            # `needs_attention` to notice a connection that cannot
            # authenticate and ask for it to be reconnected.
            return ""

    def to_python(self, value):  # noqa: ANN001, ANN201
        return value
