"""Authorisation rules for leads and the Inbox.

A lead has no client organization until it becomes one, so these are
permission checks with no tenant half. A client never sees the pipeline:
their own enquiry is not a record they are entitled to browse.
"""

from __future__ import annotations

from apps.permissions.access import has_permission
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_leads(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("leads", "view"))


def can_edit_leads(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("leads", "edit"))


def can_assign_leads(actor) -> bool:  # noqa: ANN001
    """Decide whose lead it is.

    Its own right: handing out work is a different decision from working
    on it.
    """
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("leads", "assign"))


def can_delete_leads(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("leads", "delete"))


def can_view_quotes(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("quotes", "view"))


# ---------------------------------------------------------------------------
# Quote requests
#
# A quote request is the one record in this domain a client may see, so
# these come in two halves: what staff may do, and whether this particular
# client owns this particular quote.
# ---------------------------------------------------------------------------


def can_edit_quotes(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("quotes", "edit"))


def can_assign_quotes(actor) -> bool:  # noqa: ANN001
    """Decide whose quote it is. Its own right, as with leads."""
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("quotes", "assign"))


def can_decide_quotes(actor) -> bool:  # noqa: ANN001
    """Mark a quote accepted or declined on the client's behalf.

    Separate from editing: adjusting scope is day-to-day work, recording
    that a client said yes is a commercial commitment.
    """
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("quotes", "approve"))


def can_client_see_quote(actor, quote) -> bool:  # noqa: ANN001
    """Whether this client may open this quote.

    Checked against the row rather than against a list the view built,
    so a guessed URL is refused by the same rule that filters the list.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return False

    if actor.is_staff_member:
        return False

    if not actor.is_active:
        return False
    if quote.organization_id is None:
        return quote.submitted_by_id == actor.pk
    if quote.submitted_by_id and quote.submitted_by_id != actor.pk:
        return False

    if quote.organization_id is None:
        return False

    from apps.organizations.models import ACTIVE_MEMBERSHIP_STATUSES, OrganizationMember

    return OrganizationMember.objects.filter(
        organization_id=quote.organization_id, user=actor,
        status__in=ACTIVE_MEMBERSHIP_STATUSES, organization__status="active",
    ).exists()


def can_client_decide_quote(actor, quote):
    if not can_client_see_quote(actor, quote):
        return False
    if not quote.organization_id:
        return True
    from apps.organizations.selectors import membership_for
    membership = membership_for(actor, quote.organization)
    return bool(membership and membership.role != "viewer")
