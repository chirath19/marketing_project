"""Authorisation rules for the CMS.

Website content is platform-wide — it belongs to the agency, not to any
one client — so these are permission checks with no organization half.
"""

from __future__ import annotations

from apps.permissions.access import has_permission
from apps.permissions.catalogue import permission_string


def _is_super_admin(actor) -> bool:  # noqa: ANN001
    return bool(actor and getattr(actor, "is_authenticated", False)
                and actor.is_super_admin)


def can_view_content(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("cms", "view"))


def can_edit_content(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("cms", "edit"))


def can_create_content(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("cms", "create"))


def can_delete_content(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("cms", "delete"))


def can_publish(actor) -> bool:  # noqa: ANN001
    """Putting a page live is a separate right from editing one.

    An editor can prepare a page; publishing it is the decision that puts
    it in front of the public.
    """
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("cms", "publish"))


# ---------------------------------------------------------------------------
# Blog
#
# Its own permissions, not the CMS ones. Writing articles and editing the
# marketing pages are different jobs, often different people, and an
# agency should be able to grant one without the other.
# ---------------------------------------------------------------------------


def can_view_blog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("blog", "view"))


def can_edit_blog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("blog", "edit"))


def can_create_blog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("blog", "create"))


def can_publish_blog(actor) -> bool:  # noqa: ANN001
    return _is_super_admin(actor) or has_permission(
        actor, permission_string("blog", "publish"))
