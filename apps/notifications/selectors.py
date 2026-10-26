"""Read access for notifications."""

from __future__ import annotations

from django.db.models import Count, Max, Q, QuerySet

from apps.notifications.models import Notification


def for_user(user) -> QuerySet:  # noqa: ANN001
    """A person's own notifications. Never anyone else's."""
    from apps.core.features import visible

    rows = Notification.objects.for_user(user)
    if not user or not getattr(user, "is_authenticated", False):
        return rows.none()
    categories = {"messaging": "messages", "reports": "reports", "payments": "payments",
                  "receipts": "payments", "approval": "approvals", "seo": "seo",
                  "campaign": "campaigns", "integration": "integrations"}
    hidden = [category for category, key in categories.items() if not visible(key, user)]
    rows = rows.exclude(category__in=hidden)
    for feature, segment in [("social", "social"), ("paid_ads", "paid-ads"),
                             ("email_marketing", "email-marketing"),
                             ("service_requests", "service-requests")]:
        if not visible(feature, user):
            rows = rows.exclude(Q(url__startswith=f"/staff/{segment}/") |
                                Q(url__startswith=f"/organization/{segment}/"))
    return rows.order_by("-created_at", "-pk")


def unread_count(user) -> int:  # noqa: ANN001
    """The badge number.

    Runs on every dashboard page, so it is a single indexed count and
    nothing more.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return 0
    return for_user(user).unread().count()


def get_for_user(user, pk: int):  # noqa: ANN001, ANN201
    """One of a person's own notifications, or None.

    Scoped to the signed-in user, so an id belonging to somebody else is
    simply not found — a notification is personal, and confirming one
    exists would leak that something happened.
    """
    return for_user(user).filter(pk=pk).first()


def activity_summary(user):
    """Personal counts only; client accounts never receive the agency inbox count."""
    rows = for_user(user).unread()
    counts = rows.aggregate(notifications=Count("pk"),
                            messages=Count("pk", filter=Q(category="messaging")),
                            latest_id=Max("pk"))
    counts.update(enquiries=0, quotes=0)
    if user and user.is_authenticated and user.is_staff_member:
        from apps.leads.selectors import open_quote_count, unread_count

        counts.update(enquiries=unread_count(user), quotes=open_quote_count(user))
    counts["message_threads"] = dict(rows.filter(category="messaging").order_by().values("url")
                                     .annotate(total=Count("pk")).values_list("url", "total"))
    return counts
