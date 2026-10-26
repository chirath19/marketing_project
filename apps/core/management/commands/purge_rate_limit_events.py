"""Remove throttle rows that no longer affect any decision."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import RateLimitEvent

DEFAULT_RETENTION_HOURS = 48


class Command(BaseCommand):
    help = "Delete rate-limit events older than the longest configured window."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--hours", type=int, default=DEFAULT_RETENTION_HOURS,
            help=f"Retention in hours (default: {DEFAULT_RETENTION_HOURS}).",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        cutoff = timezone.now() - timedelta(hours=options["hours"])
        stale = RateLimitEvent.objects.filter(created_at__lt=cutoff)
        count = stale.count()

        if options["dry_run"]:
            self.stdout.write(
                f"Would delete {count} rate-limit event(s) "
                f"before {cutoff:%Y-%m-%d %H:%M}."
            )
            return

        stale.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} rate-limit event(s)."))
