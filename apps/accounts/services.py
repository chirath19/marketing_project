"""Write operations for the Accounts domain.

The only place an account's state changes. Every function is
transactional, authorises through `policies.py` where an actor is
involved, and publishes a domain event rather than importing
notifications or audit directly.

Status changes never happen by assignment elsewhere in the codebase:
going through here is what guarantees `status_changed_at`, the reason,
and the event are all recorded together.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import policies
from apps.accounts.models import AccountStatus, UserType
from apps.core.events import DomainEvent, bus
from apps.organizations.models import OrganizationStatus

logger = logging.getLogger(__name__)

User = get_user_model()


class RegistrationError(Exception):
    """Registration could not be completed."""


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user: object
    organization: object
    requires_approval: bool


# The transitions that are allowed, declared as data. An attempt to move
# anywhere else raises rather than silently passing — the shape of bug
# that otherwise turns up as a reactivated account nobody authorised.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    AccountStatus.PENDING: frozenset({AccountStatus.ACTIVE, AccountStatus.DISABLED}),
    AccountStatus.ACTIVE: frozenset({AccountStatus.SUSPENDED, AccountStatus.DISABLED}),
    AccountStatus.SUSPENDED: frozenset({AccountStatus.ACTIVE, AccountStatus.DISABLED}),
    AccountStatus.DISABLED: frozenset({AccountStatus.ACTIVE}),
}


def registration_requires_approval() -> bool:
    return settings.ACCOUNTS_REGISTRATION_MODE == "approval"


@transaction.atomic
def register_client(*, email: str, password: str, full_name: str = "",
                    company_name: str = "", phone: str = "",
                    job_title: str = "") -> RegistrationResult:
    """Create a self-registered client account.

    The account starts PENDING unless the deployment is configured to
    activate automatically. Nothing is emailed; the request is published
    as an event, and the notifications domain turns that into an Inbox
    item for staff.

    The uniqueness check is belt and braces: the form checks first for a
    readable message, and the `IntegrityError` below catches the race
    where two submissions arrive at once. Only the database constraint
    can actually prevent a duplicate.

    A client company is an Organization, never a User, so registration
    creates one and makes the registrant its owner. Everything the
    platform later produces for this client hangs off that organization.
    If the company name was left blank the account is still created and
    onboarding asks for it on first sign-in — a missing company name is
    not a reason to lose a registration.
    """
    normalised = User.objects.normalize_email(email).lower().strip()
    if not normalised:
        raise RegistrationError("An email address is required.")

    status = (AccountStatus.PENDING if registration_requires_approval()
              else AccountStatus.ACTIVE)

    try:
        user = User.objects.create_user(
            email=normalised,
            password=password,
            full_name=full_name.strip(),
            phone=phone.strip(),
            job_title=job_title.strip(),
            user_type=UserType.CLIENT,
            status=status,
            status_changed_at=timezone.now(),
        )
    except IntegrityError as exc:
        # Two simultaneous submissions for the same address.
        raise RegistrationError("An account with that email already exists.") from exc

    organization = None
    if company_name.strip():
        # Imported here rather than at module scope: accounts is the lower
        # layer, and a top-level import would make the two domains
        # mutually dependent at import time.
        from apps.organizations.services import create_organization

        organization = create_organization(
            name=company_name,
            owner=user,
            actor=user,
            status=(OrganizationStatus.PENDING if status == AccountStatus.PENDING
                    else OrganizationStatus.ACTIVE),
        )

    bus.publish(DomainEvent("account.registered", {
        "user_id": user.pk,
        "email": user.email,
        "organization_id": getattr(organization, "pk", None),
        "company_name": company_name.strip(),
        "requires_approval": status == AccountStatus.PENDING,
    }))

    logger.info("Client registered: %s (status=%s, organization=%s)",
                user.email, user.status, getattr(organization, "slug", None))
    return RegistrationResult(
        user=user, organization=organization,
        requires_approval=status == AccountStatus.PENDING,
    )


@transaction.atomic
def change_status(*, user, new_status: str, actor=None, reason: str = ""):  # noqa: ANN001
    """Move an account to a new status.

    `actor` is the staff member making the change; it is None only for
    system-initiated transitions, which are logged as such.
    """
    if new_status not in AccountStatus.values:
        raise ValidationError(f"{new_status!r} is not a valid account status.")

    if actor is not None and not policies.can_change_account_status(actor, user):
        raise PermissionDenied("You may not change this account's status.")

    current = user.status
    if current == new_status:
        return user

    if new_status not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValidationError(
            f"An account cannot move from {current} to {new_status}."
        )

    user.status = new_status
    user.status_changed_at = timezone.now()
    user.status_reason = reason.strip()[:255]
    user.save(update_fields=["status", "status_changed_at", "status_reason"])

    bus.publish(DomainEvent("account.status_changed", {
        "user_id": user.pk,
        "email": user.email,
        "from_status": current,
        "to_status": new_status,
        "actor_id": getattr(actor, "pk", None),
        "reason": reason,
    }))

    logger.info("Account %s moved %s -> %s by %s",
                user.email, current, new_status,
                getattr(actor, "email", "system"))
    return user


def approve_account(*, user, actor=None, reason: str = ""):  # noqa: ANN001
    """Approve a pending registration."""
    return change_status(user=user, new_status=AccountStatus.ACTIVE,
                         actor=actor, reason=reason)


def suspend_account(*, user, actor=None, reason: str = ""):  # noqa: ANN001
    return change_status(user=user, new_status=AccountStatus.SUSPENDED,
                         actor=actor, reason=reason)


def reactivate_account(*, user, actor=None, reason: str = ""):  # noqa: ANN001
    return change_status(user=user, new_status=AccountStatus.ACTIVE,
                         actor=actor, reason=reason)


def disable_account(*, user, actor=None, reason: str = ""):  # noqa: ANN001
    """Close an account for good.

    The row is kept rather than deleted so the leads, approvals and
    messages that reference it keep their history.
    """
    return change_status(user=user, new_status=AccountStatus.DISABLED,
                         actor=actor, reason=reason)


@transaction.atomic
def update_profile(*, user, actor=None, **fields):  # noqa: ANN001
    """Update a user's own profile details.

    The company name is not here either: it belongs to the user's
    organization, which has its own settings page and its own permission
    rule. A user may be in a company without being allowed to rename it.

    The email address is not updatable here. It is the login identifier,
    and with no outbound email there is no way to verify a new address or
    to warn the old one that it changed — so a mistyped or hostile change
    would silently lock someone out of their account. Staff change it
    through the admin, deliberately.
    """
    actor = actor or user
    if not policies.can_edit_profile(actor, user):
        raise PermissionDenied("You may not edit this profile.")

    editable = {"full_name", "phone", "job_title"}
    unknown = set(fields) - editable
    if unknown:
        raise ValidationError(f"Not editable through this service: {sorted(unknown)}")

    changed = []
    for name, value in fields.items():
        cleaned = (value or "").strip()
        if getattr(user, name) != cleaned:
            setattr(user, name, cleaned)
            changed.append(name)

    if changed:
        user.save(update_fields=changed)
        bus.publish(DomainEvent("account.profile_updated", {
            "user_id": user.pk,
            "fields": sorted(changed),
            "actor_id": getattr(actor, "pk", None),
        }))

    return user


def record_password_change(*, user, actor=None) -> None:  # noqa: ANN001
    """Publish the fact that a password changed.

    The change itself is Django's — `SetPasswordForm` hashes and saves.
    This records it so audit and the Inbox can show it, since there is no
    confirmation email to serve that purpose.
    """
    bus.publish(DomainEvent("account.password_changed", {
        "user_id": user.pk,
        "actor_id": getattr(actor, "pk", None) or user.pk,
    }))
    logger.info("Password changed for %s", user.email)
