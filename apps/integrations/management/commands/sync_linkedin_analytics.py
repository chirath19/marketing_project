"""Sync LinkedIn Ads performance into PostgreSQL via the Marketing API.

Run from cron, not from a view — see docs/ANALYTICS.md. Safe to run with
no connections configured: it reports that nothing was found and exits
cleanly.
"""

from apps.integrations.management.commands._sync_base import ProviderSyncCommand
from apps.integrations.models import Provider


class Command(ProviderSyncCommand):
    help = "Sync LinkedIn Ads performance into PostgreSQL via the Marketing API."
    provider = Provider.LINKEDIN_ADS
