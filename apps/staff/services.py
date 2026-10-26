"""Write operations for the Staff domain.

Creating staff, changing what they may do, and deciding whose work they
may do it to. Every function authorises first and publishes an event
rather than importing audit or notifications.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import AccountStatus, UserType
from apps.accounts.services import change_status
from apps.core.events import DomainEvent, bus
from apps.permissions import access
from apps.permissions.models import Role
from apps.staff import policies
from apps.staff.models import (
    AssignmentRole,
    AssignmentStatus,
    StaffClientAssignment,
    StaffProfile,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class StaffError(Exception):
    """A staff account could not be created or changed."""


@transaction.atomic
def create_staff_account(
    *,
    email: str,
    actor,
    full_name: str = "",
    password: str | None = None,
    job_title: str = "",
    department: str = "",
    roles: list[Role] | None = None,
    has_all_client_access: bool = False,
    is_super_admin: bool = False,
    account_type: str = UserType.STAFF,
    django_admin_access: bool = False,
) -> StaffProfile:
    """Create a staff user and their profile.

    Staff accounts are created ACTIVE: unlike a self-registered client,
    somebody with authority has already decided this person should exist.
    The password is set by the creator and the account holder changes it
    themselves — there is no outbound email to send a setup link through.
    """
    if not policies.can_manage_staff(actor):
        raise PermissionDenied("You may not manage staff accounts.")

    if is_super_admin and not (actor and actor.is_super_admin):
        raise PermissionDenied("Only a super admin can create another super admin.")

    if account_type not in {UserType.STAFF, UserType.SYSTEM_OWNER}:
        raise ValidationError("Choose Staff or System Owner.")
    if not actor.is_super_admin and (
        account_type != UserType.STAFF or django_admin_access or has_all_client_access
    ):
        raise PermissionDenied("Only an Admin may grant platform-wide account access.")
    normalised = User.objects.normalize_email(email or "").lower().strip()
    if not normalised:
        raise ValidationError("A staff account needs an email address.")

    try:
        user = User.objects.create_user(
            email=normalised,
            password=password,
            full_name=full_name.strip(),
            user_type=UserType.SUPER_ADMIN if is_super_admin else account_type,
            status=AccountStatus.ACTIVE,
            status_changed_at=timezone.now(),
            # The Staff user type is the staff dashboard; `is_staff` is the
            # Django admin. Conflating them would hand the admin to every
            # account manager.
            is_staff=django_admin_access or is_super_admin,
            is_superuser=is_super_admin,
        )
    except IntegrityError as exc:
        raise StaffError("An account with that email already exists.") from exc

    profile = StaffProfile.objects.create(
        user=user,
        job_title=job_title.strip(),
        department=department.strip(),
        has_all_client_access=has_all_client_access
        or is_super_admin
        or account_type == UserType.SYSTEM_OWNER,
    )

    if roles:
        assign_roles(profile=profile, roles=roles, actor=actor)

    bus.publish(
        DomainEvent(
            "staff.created",
            {
                "user_id": user.pk,
                "email": user.email,
                "is_super_admin": is_super_admin,
                "actor_id": getattr(actor, "pk", None),
            },
        )
    )
    logger.info("Staff account created: %s by %s", user.email, getattr(actor, "email", "system"))
    return profile


@transaction.atomic
def update_staff(*, profile: StaffProfile, actor, **fields) -> StaffProfile:
    if not policies.can_manage_staff(actor):
        raise PermissionDenied("You may not manage staff accounts.")

    _protect_target(actor, profile)
    account_fields = {key: fields.pop(key) for key in ("full_name", "email") if key in fields}
    editable = {"job_title", "department", "notes", "has_all_client_access"}
    unknown = set(fields) - editable
    if unknown:
        raise ValidationError(f"Not editable through this service: {sorted(unknown)}")

    if "has_all_client_access" in fields and not (actor and actor.is_super_admin):
        raise PermissionDenied("Only a super admin can grant access to every client.")

    account_changed = []
    for key, value in account_fields.items():
        cleaned = (value or "").strip()
        if not cleaned:
            continue
        if key == "email":
            cleaned = User.objects.normalize_email(cleaned).lower()
        if getattr(profile.user, key) != cleaned:
            setattr(profile.user, key, cleaned)
            account_changed.append(key)
    if account_changed:
        profile.user.full_clean()
        profile.user.save(update_fields=account_changed)

    changed = []
    for name, value in fields.items():
        cleaned = value if isinstance(value, bool) else (value or "").strip()
        if getattr(profile, name) != cleaned:
            setattr(profile, name, cleaned)
            changed.append(name)

    if changed or account_changed:
        profile.save(update_fields=[*changed, "updated_at"])
        access.clear_cache(profile.user)
        bus.publish(
            DomainEvent(
                "staff.updated",
                {
                    "user_id": profile.user_id,
                    "fields": sorted(changed + account_changed),
                    "actor_id": getattr(actor, "pk", None),
                },
            )
        )

    return profile


def activate_staff(*, profile: StaffProfile, actor, reason: str = ""):
    """Let a staff account sign in again.

    Delegates to the accounts service, which owns the status machine —
    there is one implementation of what a status change means, not two.
    """
    if not policies.can_manage_staff(actor):
        raise PermissionDenied("You may not manage staff accounts.")
    return change_status(
        user=profile.user, new_status=AccountStatus.ACTIVE, actor=actor, reason=reason
    )


def deactivate_staff(*, profile: StaffProfile, actor, reason: str = ""):
    """Stop a staff account signing in, keeping their history."""
    if not policies.can_manage_staff(actor):
        raise PermissionDenied("You may not manage staff accounts.")
    return change_status(
        user=profile.user, new_status=AccountStatus.SUSPENDED, actor=actor, reason=reason
    )


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@transaction.atomic
def assign_roles(*, profile: StaffProfile, roles: list[Role], actor) -> StaffProfile:
    """Replace a staff member's roles with exactly this set."""
    if not policies.can_assign_roles(actor):
        raise PermissionDenied("You may not assign roles.")

    _protect_target(actor, profile)
    if not actor.is_super_admin:
        held = access.permission_codenames_for(actor)
        if any(not role.permission_codenames <= held for role in roles):
            raise PermissionDenied("You can only delegate permissions you hold.")
    profile.roles.set(roles)
    access.clear_cache(profile.user)

    bus.publish(
        DomainEvent(
            "staff.roles_changed",
            {
                "user_id": profile.user_id,
                "roles": sorted(role.name for role in roles),
                "actor_id": getattr(actor, "pk", None),
            },
        )
    )
    logger.info("Roles for %s set to %s", profile.user.email, [role.name for role in roles])
    return profile


# ---------------------------------------------------------------------------
# Client assignments
# ---------------------------------------------------------------------------


@transaction.atomic
def assign_to_organization(
    *,
    profile: StaffProfile,
    organization,
    actor,  # noqa: ANN001
    role: str = AssignmentRole.SPECIALIST,
    is_primary: bool = False,
) -> StaffClientAssignment:
    """Give a staff member access to one client's work."""
    if not policies.can_assign_clients(actor):
        raise PermissionDenied("You may not assign staff to clients.")

    if role not in AssignmentRole.values:
        raise ValidationError(f"{role!r} is not a valid assignment role.")

    assignment, created = StaffClientAssignment.objects.get_or_create(
        staff=profile,
        organization=organization,
        defaults={
            "role": role,
            "is_primary": is_primary,
            "assigned_by": actor if getattr(actor, "pk", None) else None,
        },
    )

    if not created:
        # Re-assigning someone whose assignment had ended restores it
        # rather than failing on the unique constraint.
        assignment.status = AssignmentStatus.ACTIVE
        assignment.role = role
        assignment.is_primary = is_primary
        assignment.ended_at = None
        assignment.save(update_fields=["status", "role", "is_primary", "ended_at", "updated_at"])

    if is_primary:
        # One first point of contact per client.
        StaffClientAssignment.objects.filter(
            organization=organization,
            is_primary=True,
        ).exclude(pk=assignment.pk).update(is_primary=False)

    access.clear_cache(profile.user)
    bus.publish(
        DomainEvent(
            "staff.assigned_to_client",
            {
                "user_id": profile.user_id,
                "organization_id": organization.pk,
                "role": role,
                "actor_id": getattr(actor, "pk", None),
            },
        )
    )
    logger.info("Assigned %s to %s as %s", profile.user.email, organization, role)
    return assignment


@transaction.atomic
def end_assignment(*, assignment: StaffClientAssignment, actor) -> StaffClientAssignment:
    """Remove a staff member's access to a client.

    The row is kept with status ENDED rather than deleted, so "who worked
    on this account last year" remains answerable. Access stops on the
    staff member's next request.
    """
    if not policies.can_assign_clients(actor):
        raise PermissionDenied("You may not assign staff to clients.")

    assignment.status = AssignmentStatus.ENDED
    assignment.ended_at = timezone.now()
    assignment.is_primary = False
    assignment.save(update_fields=["status", "ended_at", "is_primary", "updated_at"])

    access.clear_cache(assignment.staff.user)
    bus.publish(
        DomainEvent(
            "staff.unassigned_from_client",
            {
                "user_id": assignment.staff.user_id,
                "organization_id": assignment.organization_id,
                "actor_id": getattr(actor, "pk", None),
            },
        )
    )
    return assignment


@transaction.atomic
def approve_client_registration(*, actor, user):
    """Activate a registration and its pending owned workspace together."""
    from apps.organizations.models import MemberRole, OrganizationMember, OrganizationStatus
    from apps.organizations.services import change_organization_status

    if not (actor.is_super_admin or actor.is_system_owner):
        raise PermissionDenied("Only an Admin or System Owner may approve registrations.")
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.is_client or user.status != AccountStatus.PENDING:
        raise ValidationError("This client is not awaiting registration approval.")
    change_status(
        user=user,
        new_status=AccountStatus.ACTIVE,
        actor=actor,
        reason="Registration approved in the staff dashboard.",
    )
    for member in OrganizationMember.objects.filter(
        user=user, role=MemberRole.OWNER, organization__status=OrganizationStatus.PENDING
    ):
        change_organization_status(
            organization=member.organization, actor=actor, new_status=OrganizationStatus.ACTIVE
        )
    return user


def _protect_target(actor, profile):
    if not actor.is_super_admin and (profile.user.is_super_admin or profile.user.is_system_owner):
        raise PermissionDenied("Only an Admin may manage administrator or owner accounts.")


@transaction.atomic
def remove_staff_account(*, actor, profile):
    """Remove sign-in access while preserving authorship of client records."""
    if not access.has_permission(actor, "staff_delete"):
        raise PermissionDenied
    _protect_target(actor, profile)
    return change_status(
        user=profile.user,
        new_status=AccountStatus.DISABLED,
        actor=actor,
        reason="Account removed from staff administration",
    )
