"""Creating and clearing notifications.

`notify_permission_holders` is how the rest of the platform raises
something for staff attention: it names a permission rather than a list
of people, so the right people get told as roles change without any
caller having to know who they are.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notification, NotificationLevel

logger = logging.getLogger(__name__)
User = get_user_model()


@transaction.atomic
def notify(*, recipient, title: str, body: str = "", url: str = "",  # noqa: ANN001
           level: str = NotificationLevel.INFO,
           category: str = "") -> Notification:
    return Notification.objects.create(
        recipient=recipient, title=title[:200], body=body[:300],
        url=url[:500], level=level, category=category,
    )


@transaction.atomic
def notify_permission_holders(*, permission: str, title: str, body: str = "",
                              url: str = "",
                              level: str = NotificationLevel.INFO,
                              category: str = "",
                              exclude=None, organization=None) -> int:  # noqa: ANN001
    """Tell everyone who holds a permission.

    Resolved through the same access rules as everything else, so a
    notification cannot reach someone who would not be allowed to open
    what it points at. Suspended accounts are skipped — telling somebody
    who cannot sign in is noise for whoever eventually reads it.
    """
    from apps.accounts.models import AccountStatus
    from apps.permissions import access

    recipients = []
    staff = (
        User.objects.filter(status=AccountStatus.ACTIVE)
        .exclude(pk=getattr(exclude, "pk", None))
        .select_related("staff_profile")
    )

    for user in staff:
        if not user.is_staff_member:
            continue
        if access.can(user, permission, organization):
            recipients.append(user)

    if not recipients:
        # Not an error: a small agency may genuinely have nobody holding
        # a given permission yet. The record still exists in the Inbox.
        logger.info("No recipients hold %s; notification not fanned out.",
                    permission)
        return 0

    Notification.objects.bulk_create([
        Notification(recipient=user, title=title[:200], body=body[:300],
                     url=url[:500], level=level, category=category)
        for user in recipients
    ])
    return len(recipients)


@transaction.atomic
def mark_all_read(*, user) -> int:  # noqa: ANN001
    from apps.notifications.selectors import for_user

    return for_user(user).unread().update(
        read_at=timezone.now()
    )


def mark_related_read(*, user, category, url, through=None):
    """Opening work acknowledges that person's related alerts, not teammates'."""
    through = through or timezone.now()
    return Notification.objects.for_user(user).unread().filter(
        category=category, url=url, created_at__lte=through
    ).update(read_at=through)
