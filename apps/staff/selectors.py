"""Read access for the Staff domain."""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.staff.models import ACCESS_GRANTING_STATUSES, StaffClientAssignment, StaffProfile


def visible_staff(actor) -> QuerySet:  # noqa: ANN001
    """Staff profiles the actor may list.

    Staff administration is platform-wide, not client-scoped, so this is
    an all-or-nothing read gated by the permission.
    """
    from apps.staff import policies

    if not policies.can_view_staff(actor):
        return StaffProfile.objects.none()

    return (
        StaffProfile.objects.select_related("user")
        .prefetch_related("roles")
        .annotate(
            client_count=Count(
                "assignments",
                filter=Q(assignments__status__in=ACCESS_GRANTING_STATUSES),
                distinct=True,
            )
        )
        .order_by("user__email")
    )


def get_staff(actor, pk: int):  # noqa: ANN001, ANN201
    return visible_staff(actor).filter(pk=pk).first()


def assignments_for(profile: StaffProfile) -> QuerySet:
    return (
        StaffClientAssignment.objects.filter(staff=profile)
        .select_related("organization", "assigned_by")
        .order_by("status", "organization__name")
    )


def assigned_organizations(user) -> QuerySet:  # noqa: ANN001
    """Client organizations a staff member currently works on."""
    from apps.organizations.models import Organization

    profile = getattr(user, "staff_profile", None)
    if profile is None:
        return Organization.objects.none()

    if profile.has_all_client_access:
        return Organization.objects.all()

    return Organization.objects.filter(
        staff_assignments__staff=profile,
        staff_assignments__status__in=ACCESS_GRANTING_STATUSES,
    ).distinct()


def staff_for_organization(organization) -> QuerySet:  # noqa: ANN001
    return (
        StaffClientAssignment.objects.filter(
            organization=organization, status__in=ACCESS_GRANTING_STATUSES,
        )
        .select_related("staff__user")
        .order_by("-is_primary", "role")
    )
