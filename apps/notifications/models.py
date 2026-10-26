"""In-app notifications.

The platform sends nothing outbound, so this is the whole delivery
mechanism: a row in PostgreSQL and a badge in the dashboard. A
notification is a pointer at something that needs attention, not a copy
of it — the detail lives on the thing it points at, so a notification can
never go stale or disagree with the record.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class NotificationLevel(models.TextChoices):
    INFO = "info", _("Information")
    ACTION = "action", _("Needs action")
    WARNING = "warning", _("Warning")


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(read_at__isnull=True)

    def for_user(self, user):  # noqa: ANN001
        if not user or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(recipient=user)


class Notification(TimeStampedModel):
    """One notification for one person.

    Fanned out per recipient rather than shared, so "read" means read by
    that person — a shared row would mark an item read for the whole team
    the moment anyone opened it.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications", verbose_name=_("recipient"),
    )

    title = models.CharField(_("title"), max_length=200)
    body = models.CharField(_("detail"), max_length=300, blank=True)
    url = models.CharField(
        _("link"), max_length=500, blank=True,
        help_text=_("Where to go to deal with it."),
    )
    level = models.CharField(_("level"), max_length=20,
                             choices=NotificationLevel.choices,
                             default=NotificationLevel.INFO)
    category = models.CharField(
        _("category"), max_length=40, blank=True, db_index=True,
        help_text=_("What produced it, e.g. “lead”. Used for filtering."),
    )

    read_at = models.DateTimeField(_("read"), null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at", "-pk"]
        indexes = [
            # The badge query: unread, for one person, newest first.
            models.Index(fields=["recipient", "read_at", "-created_at"],
                         name="notif_recipient_unread_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.recipient}: {self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at", "updated_at"])
