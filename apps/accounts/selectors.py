"""Read access for the Accounts domain.

Every queryset returned from here is scoped to what the requesting actor
may see. Views, serializers and templates read through these functions,
never through the manager directly.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.accounts.models import AccountStatus, UserType

User = get_user_model()


def get_by_email(email: str):  # noqa: ANN201
    """Find an account by address, case-insensitively.

    Returns None rather than raising: callers are usually deciding how to
    respond to an unauthenticated request, where "no such user" is an
    ordinary answer and an exception would be noise.
    """
    normalised = (email or "").strip().lower()
    if not normalised:
        return None
    return User.objects.filter(email=normalised).first()


def email_is_taken(email: str) -> bool:
    normalised = (email or "").strip().lower()
    return bool(normalised) and User.objects.filter(email=normalised).exists()


def visible_accounts(actor) -> QuerySet:  # noqa: ANN001
    """The accounts an actor may list.

    Staff see everyone; anyone else sees only themselves. The client
    organization scoping that will narrow this further arrives with the
    organizations phase.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return User.objects.none()

    if actor.is_staff_member:
        return User.objects.all()

    return User.objects.filter(pk=actor.pk)


def pending_approvals(actor) -> QuerySet:  # noqa: ANN001
    """Client registrations waiting on a staff decision.

    Ordered oldest first: the person who has been waiting longest is the
    one to deal with next.
    """
    return (
        visible_accounts(actor)
        .filter(status=AccountStatus.PENDING, user_type=UserType.CLIENT)
        .order_by("date_joined")
    )


def pending_approval_count(actor) -> int:  # noqa: ANN001
    return pending_approvals(actor).count()
