"""Authorisation rules for the Accounts domain.

Pure predicates of the form `can_<verb>(actor, obj) -> bool`, called from
`services.py` so every entry point — web, API, admin action, management
command — is covered by the same rule.

These are deliberately conservative. The full RBAC tables and per-user
overrides arrive with the permissions phase; until then, anything beyond
"your own account" requires staff.
"""

from __future__ import annotations

from apps.accounts.models import UserType


def _is_staff(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False) and actor.is_staff_member)


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False) and actor.is_super_admin)


def can_view_account(actor, user) -> bool:  # noqa: ANN001
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    return actor.pk == user.pk or _is_staff(actor)


def can_edit_profile(actor, user) -> bool:  # noqa: ANN001
    """Your own profile, or anyone's if you are staff."""
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    return actor.pk == user.pk or _is_staff(actor)


def can_change_account_status(actor, user) -> bool:  # noqa: ANN001
    """Approve, suspend, reactivate or disable an account.

    Two rules beyond "staff only":

    * Nobody changes their own status. Otherwise a suspended staff member
      with a live session could lift their own suspension.
    * Only a super admin may act on another staff member or super admin.
      A staff account must not be able to disable its own supervisor.
    """
    if not _is_staff(actor):
        return False

    if actor.pk == user.pk:
        return False

    if user.is_super_admin or user.is_system_owner:
        return _is_super_admin(actor)
    if user.user_type == UserType.STAFF:
        from apps.permissions.access import has_permission

        return _is_super_admin(actor) or (
            actor.is_system_owner and has_permission(actor, "staff_manage")
        )

    return True


def can_change_password(actor, user) -> bool:  # noqa: ANN001
    """Only the account holder, and only knowing the current password.

    Staff do not set client passwords: with no outbound email there is no
    safe way to deliver a new one, so a staff-initiated reset is a
    separate, auditable flow for a later phase rather than a quiet
    capability here.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    return actor.pk == user.pk
