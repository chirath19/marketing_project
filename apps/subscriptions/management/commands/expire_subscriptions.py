"""Close services whose agreed end date has passed.

Expiry is a recorded status rather than something worked out at read
time, so the history says when it happened and the client's workspace
stops showing an area they are no longer paying for.

There is no scheduler in this version — that is a deliberate constraint,
not an oversight — so this runs from cron, a Railway scheduled job, or a
person. It is safe to run repeatedly: a service only expires once.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.subscriptions import services


class Command(BaseCommand):
    help = "Mark client services whose agreed end date has passed as expired."

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List what would expire without changing anything.",
        )

    def handle(self, *args, **options) -> None:
        from apps.subscriptions.models import ClientSubscription

        if options["dry_run"]:
            due = ClientSubscription.objects.due_to_expire().select_related(
                "organization")
            for subscription in due:
                self.stdout.write(
                    f"would expire: {subscription.organization.label} — "
                    f"{subscription.name} (ended {subscription.ends_on})"
                )
            self.stdout.write(self.style.NOTICE(f"{len(due)} due."))
            return

        expired = services.expire_due()
        for subscription in expired:
            self.stdout.write(
                f"expired: {subscription.organization.label} — {subscription.name}"
            )
        self.stdout.write(self.style.SUCCESS(f"{len(expired)} expired."))
