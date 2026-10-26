"""Read access for the Organizations domain.

Every queryset returned from here is already scoped to the requesting
actor and `select_related` / `prefetch_related` complete. Views,
serializers and templates read through these functions, never through a
manager directly — that is what keeps the isolation rule in one place.
"""

from __future__ import annotations

from django.db.models import Count, Q, QuerySet

from apps.organizations.models import (
    ACTIVE_MEMBERSHIP_STATUSES,
    MANAGING_ROLES,
    MemberRole,
    Organization,
    OrganizationMember,
    OrganizationStatus,
)


def visible_organizations(actor) -> QuerySet:  # noqa: ANN001
    return Organization.objects.visible_to(actor)


def get_organization(actor, slug: str):  # noqa: ANN001, ANN201
    """One organization, or None if the actor may not see it.

    Returning None rather than raising keeps the caller's 404-vs-403
    decision in the view, where it belongs. Note that it is resolved from
    the actor's own memberships — a slug in the URL is never trusted on
    its own.
    """
    return visible_organizations(actor).filter(slug=slug).first()


def organizations_for_user(user) -> QuerySet:  # noqa: ANN001
    """The organizations a client actively belongs to, newest first.

    Used to decide which organization a session is working in. Staff are
    not members of anything, so this is empty for them by design.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return Organization.objects.none()

    return (
        Organization.objects.filter(
            memberships__user=user,
            memberships__status__in=ACTIVE_MEMBERSHIP_STATUSES,
        )
        .distinct()
        .order_by("name")
    )


def primary_organization_for(user):  # noqa: ANN001, ANN201
    """The organization a client lands in by default.

    Owned organizations win over ones they were added to, so someone who
    registered their own company sees it first.
    """
    memberships = (
        OrganizationMember.objects.filter(
            user=user, status__in=ACTIVE_MEMBERSHIP_STATUSES,
        )
        .select_related("organization")
        .order_by("role", "organization__name")
    )

    owned = next((m for m in memberships if m.role == MemberRole.OWNER), None)
    if owned:
        return owned.organization

    first = memberships.first()
    return first.organization if first else None


def membership_for(user, organization):  # noqa: ANN001, ANN201
    """An actor's active membership of an organization, or None."""
    if not user or not getattr(user, "is_authenticated", False) or organization is None:
        return None

    return (
        OrganizationMember.objects.filter(
            user=user, organization=organization,
            status__in=ACTIVE_MEMBERSHIP_STATUSES,
        )
        .select_related("organization", "user")
        .first()
    )


def members_of(actor, organization) -> QuerySet:  # noqa: ANN001
    """The people in an organization, as the actor is allowed to see them."""
    return (
        OrganizationMember.objects.visible_to(actor)
        .filter(organization=organization)
        .select_related("user", "organization", "invited_by")
        .order_by("role", "user__email")
    )


def active_managers_of(organization) -> QuerySet:  # noqa: ANN001
    return OrganizationMember.objects.filter(
        organization=organization,
        status__in=ACTIVE_MEMBERSHIP_STATUSES,
        role__in=MANAGING_ROLES,
    ).select_related("user")


def active_owner_count(organization) -> int:
    return OrganizationMember.objects.filter(
        organization=organization,
        status__in=ACTIVE_MEMBERSHIP_STATUSES,
        role=MemberRole.OWNER,
    ).count()


def user_needs_onboarding(user) -> bool:
    """Whether a client still has to set their organization up.

    True only for clients: staff do not belong to a client company, and
    an anonymous visitor has nothing to onboard.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_client:
        return False
    return not organizations_for_user(user).exists()


def pending_onboarding(actor) -> QuerySet:  # noqa: ANN001
    """Client organizations created but not yet activated.

    Exposed here rather than letting a caller import OrganizationStatus:
    what counts as "not onboarded yet" is this domain's business, and a
    dashboard should not have to know the status vocabulary.
    """
    return visible_organizations(actor).filter(status=OrganizationStatus.PENDING)


def staff_organization_list(actor, *, search: str = "", status: str = "") -> QuerySet:  # noqa: ANN001
    """The staff-facing client list.

    Annotated with the member count in the same query, so rendering the
    list does not issue one count per row.
    """
    queryset = (
        visible_organizations(actor)
        .annotate(
            member_count=Count(
                "memberships",
                filter=Q(memberships__status__in=ACTIVE_MEMBERSHIP_STATUSES),
                distinct=True,
            )
        )
        .order_by("name")
    )

    if status and status in OrganizationStatus.values:
        queryset = queryset.filter(status=status)

    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(display_name__icontains=search)
            | Q(slug__icontains=search)
        )

    return queryset
