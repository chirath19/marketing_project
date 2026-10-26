"""Sync GA4 website reporting into PostgreSQL via the GA4 Data API.

Run from cron, not from a view — see docs/ANALYTICS.md for the scheduling
story. Safe to run with no connections configured: it reports that
nothing was found and exits cleanly, which is what lets this be wired
into Railway's scheduler before a single client has a real connection.
"""

from apps.integrations.management.commands._sync_base import ProviderSyncCommand
from apps.integrations.models import Provider


class Command(ProviderSyncCommand):
    help = "Sync GA4 website reporting into PostgreSQL via the GA4 Data API."
    provider = Provider.GOOGLE_ANALYTICS
