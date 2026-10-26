"""Shared plumbing for the per-provider sync commands.

Each `sync_*` command is a thin wrapper naming one provider; this base
class is where the actual loop lives, so adding a fifth provider command
later is a five-line file, not a second copy of this logic.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.integrations.models import IntegrationConnection, Provider, SyncStatus
from apps.integrations.services import run_sync


class ProviderSyncCommand(BaseCommand):
    #: Set on each subclass to one `Provider` value.
    provider: str = ""

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument(
            "--days", type=int, default=7,
            help="How many days back to pull, ending today. Default 7.",
        )
        parser.add_argument(
            "--organization", type=str, default="",
            help="Sync one client only, by organization slug. Default: "
                 "every client with a connection for this provider.",
        )

    def handle(self, *args, **options) -> None:
        days = options["days"]
        slug = options["organization"]

        if slug:
            from apps.organizations.models import Organization

            organizations = Organization.objects.filter(slug=slug)
            if not organizations.exists():
                self.stderr.write(self.style.ERROR(f"No organization '{slug}'."))
                return
        elif self.provider == Provider.RUDDERSTACK:
            organizations = [None]
        else:
            organizations = list(
                IntegrationConnection.objects
                .filter(provider=self.provider)
                .values_list("organization", flat=True)
            )
            organizations = (
                __import__("apps.organizations.models", fromlist=["Organization"])
                .Organization.objects.filter(pk__in=organizations)
            )

        if not organizations:
            self.stdout.write("No connections configured for this provider yet.")
            return

        counts = dict.fromkeys(SyncStatus.values, 0)
        for organization in organizations:
            run = run_sync(provider=self.provider, organization=organization,
                           days=days)
            counts[run.status] += 1
            label = organization.label if organization else "(agency-wide)"
            self.stdout.write(
                f"  {label}: {run.get_status_display()}"
                + (f" — {run.error_summary}" if run.error_summary else "")
            )

        summary = ", ".join(f"{count} {status}" for status, count in counts.items()
                            if count)
        self.stdout.write(self.style.SUCCESS(f"Done. {summary}."))
