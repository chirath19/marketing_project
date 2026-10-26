"""Write operations for the Organizations domain.

The only place an organization or a membership changes. Each function is
transactional, authorises through `policies.py`, and publishes a domain
event instead of importing notifications or audit directly.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.events import DomainEvent, bus
from apps.organizations import policies, selectors
from apps.organizations.models import (
    MemberRole,
    MemberStatus,
    Organization,
    OrganizationMember,
    OrganizationStatus,
)

logger = logging.getLogger(__name__)


ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    OrganizationStatus.PENDING: frozenset({OrganizationStatus.ACTIVE,
                                           OrganizationStatus.ARCHIVED}),
    OrganizationStatus.ACTIVE: frozenset({OrganizationStatus.SUSPENDED,
                                          OrganizationStatus.ARCHIVED}),
    OrganizationStatus.SUSPENDED: frozenset({OrganizationStatus.ACTIVE,
                                             OrganizationStatus.ARCHIVED}),
    OrganizationStatus.ARCHIVED: frozenset({OrganizationStatus.ACTIVE}),
}

EDITABLE_PROFILE_FIELDS = frozenset({
    "name", "display_name", "website", "email", "phone",
    "address_line1", "address_line2", "city", "region", "postal_code", "country",
})


def _unique_slug(name: str) -> str:
    """Build a slug that is not already taken.

    The candidate set is read inside the caller's transaction and the
    database's unique constraint is the real guarantee; this just avoids
    an error on the common case of two clients with similar names.
    """
    taken = set(
        Organization.objects.filter(slug__startswith=Organization.build_slug(name))
        .values_list("slug", flat=True)
    )
    return Organization.build_slug(name, taken=taken)


@transaction.atomic
def create_organization(*, name: str, owner=None, actor=None,  # noqa: ANN001
                        status: str | None = None, **profile) -> Organization:
    """Create a client company, optionally with its first owner.

    Called from two places: registration, where the client becomes the
    owner, and the staff dashboard, where staff set a company up before
    anyone from it has an account.
    """
    cleaned_name = (name or "").strip()
    if not cleaned_name:
        raise ValidationError("An organization needs a name.")

    unknown = set(profile) - EDITABLE_PROFILE_FIELDS
    if unknown:
        raise ValidationError(f"Not settable here: {sorted(unknown)}")

    organization = Organization.objects.create(
        name=cleaned_name,
        slug=_unique_slug(cleaned_name),
        status=status or OrganizationStatus.PENDING,
        status_changed_at=timezone.now(),
        **{key: (value or "").strip() for key, value in profile.items()},
    )

    if owner is not None:
        add_member(
            organization=organization, user=owner, role=MemberRole.OWNER,
            actor=actor or owner, _bootstrap=True,
        )

    bus.publish(DomainEvent("organization.created", {
        "organization_id": organization.pk,
        "slug": organization.slug,
        "name": organization.name,
        "owner_id": getattr(owner, "pk", None),
        "actor_id": getattr(actor, "pk", None),
    }))

    logger.info("Organization created: %s (%s)", organization.name, organization.slug)
    return organization


@transaction.atomic
def update_organization(*, organization: Organization, actor=None, **fields) -> Organization:  # noqa: ANN001
    """Update a company's own details.

    `notes` is not accepted here: internal notes are staff-only and go
    through `update_internal_notes`, which checks a different rule.
    """
    if not policies.can_manage_organization(actor, organization):
        raise PermissionDenied("You may not edit this organization.")

    unknown = set(fields) - EDITABLE_PROFILE_FIELDS
    if unknown:
        raise ValidationError(f"Not editable through this service: {sorted(unknown)}")

    changed = []
    for field, value in fields.items():
        cleaned = (value or "").strip()
        if field == "name" and not cleaned:
            raise ValidationError("An organization needs a name.")
        if getattr(organization, field) != cleaned:
            setattr(organization, field, cleaned)
            changed.append(field)

    if changed:
        organization.save(update_fields=[*changed, "updated_at"])
        bus.publish(DomainEvent("organization.updated", {
            "organization_id": organization.pk,
            "fields": sorted(changed),
            "actor_id": getattr(actor, "pk", None),
        }))

    return organization


@transaction.atomic
def update_internal_notes(*, organization: Organization, actor, notes: str) -> Organization:  # noqa: ANN001
    if not policies.can_edit_internal_notes(actor, organization):
        raise PermissionDenied("Internal notes are staff only.")

    organization.notes = notes
    organization.save(update_fields=["notes", "updated_at"])
    return organization


@transaction.atomic
def change_organization_status(*, organization: Organization, new_status: str,  # noqa: ANN001
                               actor=None, reason: str = "") -> Organization:
    if new_status not in OrganizationStatus.values:
        raise ValidationError(f"{new_status!r} is not a valid organization status.")

    if not policies.can_change_organization_status(actor, organization):
        raise PermissionDenied("You may not change this organization's status.")

    current = organization.status
    if current == new_status:
        return organization

    if new_status not in ALLOWED_STATUS_TRANSITIONS.get(current, frozenset()):
        raise ValidationError(
            f"An organization cannot move from {current} to {new_status}."
        )

    organization.status = new_status
    organization.status_changed_at = timezone.now()
    organization.save(update_fields=["status", "status_changed_at", "updated_at"])

    bus.publish(DomainEvent("organization.status_changed", {
        "organization_id": organization.pk,
        "from_status": current,
        "to_status": new_status,
        "actor_id": getattr(actor, "pk", None),
        "reason": reason,
    }))

    logger.info("Organization %s moved %s -> %s", organization.slug, current, new_status)
    return organization


def activate_organization(*, organization, actor=None, reason: str = ""):  # noqa: ANN001
    return change_organization_status(
        organization=organization, new_status=OrganizationStatus.ACTIVE,
        actor=actor, reason=reason,
    )


def suspend_organization(*, organization, actor=None, reason: str = ""):  # noqa: ANN001
    return change_organization_status(
        organization=organization, new_status=OrganizationStatus.SUSPENDED,
        actor=actor, reason=reason,
    )


def archive_organization(*, organization, actor=None, reason: str = ""):  # noqa: ANN001
    return change_organization_status(
        organization=organization, new_status=OrganizationStatus.ARCHIVED,
        actor=actor, reason=reason,
    )


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


@transaction.atomic
def add_member(*, organization: Organization, user, role: str = MemberRole.MEMBER,  # noqa: ANN001
               actor=None, job_title: str = "", _bootstrap: bool = False) -> OrganizationMember:
    """Put a person in an organization.

    `_bootstrap` is for the first owner, created alongside the
    organization itself. At that moment nobody can manage it yet, so the
    usual permission check would refuse the very call that makes
    management possible.
    """
    if role not in MemberRole.values:
        raise ValidationError(f"{role!r} is not a valid role.")

    if not _bootstrap and not policies.can_manage_members(actor, organization):
        raise PermissionDenied("You may not manage this organization's members.")

    existing = OrganizationMember.objects.filter(
        organization=organization, user=user
    ).first()

    if existing is not None:
        # Re-adding someone who previously left reactivates their place
        # rather than failing on the unique constraint.
        if existing.status == MemberStatus.ACTIVE:
            raise ValidationError("That person is already a member of this organization.")

        existing.status = MemberStatus.ACTIVE
        existing.role = role
        existing.save(update_fields=["status", "role", "updated_at"])
        member = existing
    else:
        member = OrganizationMember.objects.create(
            organization=organization, user=user, role=role,
            job_title=job_title.strip(),
            invited_by=actor if getattr(actor, "pk", None) else None,
        )

    bus.publish(DomainEvent("organization.member_added", {
        "organization_id": organization.pk,
        "user_id": user.pk,
        "role": role,
        "actor_id": getattr(actor, "pk", None),
    }))

    logger.info("Member added: %s to %s as %s", user, organization.slug, role)
    return member


@transaction.atomic
def change_member_role(*, membership: OrganizationMember, new_role: str, actor=None):  # noqa: ANN001
    if new_role not in MemberRole.values:
        raise ValidationError(f"{new_role!r} is not a valid role.")

    if not policies.can_change_member_role(actor, membership):
        raise PermissionDenied("You may not change this member's role.")

    if membership.role == new_role:
        return membership

    _guard_last_owner(membership, becoming=new_role)

    previous = membership.role
    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])

    bus.publish(DomainEvent("organization.member_role_changed", {
        "organization_id": membership.organization_id,
        "user_id": membership.user_id,
        "from_role": previous,
        "to_role": new_role,
        "actor_id": getattr(actor, "pk", None),
    }))
    return membership


@transaction.atomic
def remove_member(*, membership: OrganizationMember, actor=None):  # noqa: ANN001
    """Remove someone from an organization.

    The row is kept with status REMOVED rather than deleted, so that the
    approvals and messages attributed to them keep their author.
    """
    if not policies.can_remove_member(actor, membership):
        raise PermissionDenied("You may not remove this member.")

    _guard_last_owner(membership, becoming=None)

    membership.status = MemberStatus.REMOVED
    membership.save(update_fields=["status", "updated_at"])

    bus.publish(DomainEvent("organization.member_removed", {
        "organization_id": membership.organization_id,
        "user_id": membership.user_id,
        "actor_id": getattr(actor, "pk", None),
    }))
    return membership


@transaction.atomic
def suspend_member(*, membership: OrganizationMember, actor=None):  # noqa: ANN001
    if not policies.can_manage_members(actor, membership.organization):
        raise PermissionDenied("You may not manage this organization's members.")

    _guard_last_owner(membership, becoming=None)

    membership.status = MemberStatus.SUSPENDED
    membership.save(update_fields=["status", "updated_at"])
    return membership


def _guard_last_owner(membership: OrganizationMember, *, becoming: str | None) -> None:
    """Refuse to leave an organization with nobody in charge.

    An organization with no active owner cannot add members, change its
    own details or hand over control — it would need staff intervention
    to recover. Cheaper to refuse the move.
    """
    if membership.role != MemberRole.OWNER or not membership.is_active:
        return

    if becoming == MemberRole.OWNER:
        return

    if selectors.active_owner_count(membership.organization) <= 1:
        raise ValidationError(
            "This is the organization's only owner. Make someone else an "
            "owner first."
        )
