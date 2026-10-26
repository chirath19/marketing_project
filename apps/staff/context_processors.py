"""Navigation context for the admin shell.

Resolved once per request and shared by the sidebar and the mobile
drawer, so the two can never show different menus. Lazy, so the public
site and the API pay nothing for it.
"""

from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject

from apps.staff.navigation import visible_navigation


def _unread_notifications(user) -> int:  # noqa: ANN001
    from apps.notifications.selectors import unread_count

    return unread_count(user)


def _unread_enquiries(user) -> int:  # noqa: ANN001
    from apps.leads.selectors import unread_count

    return unread_count(user)


def admin_navigation(request: HttpRequest) -> dict:
    """Navigation and the two unread counts the shell badges.

    All three are lazy: the public site and the API render none of them
    and should pay nothing for them.
    """
    user = getattr(request, "user", None)

    from apps.notifications.selectors import activity_summary

    return {
        "admin_navigation": SimpleLazyObject(lambda: visible_navigation(user)),
        "activity": SimpleLazyObject(lambda: activity_summary(user)),
        "unread_notifications": SimpleLazyObject(lambda: _unread_notifications(user)),
        "unread_enquiries": SimpleLazyObject(lambda: _unread_enquiries(user)),
        "search_query": request.GET.get("q", "") if request.method == "GET" else "",
    }
