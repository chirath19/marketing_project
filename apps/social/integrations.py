"""Boundary for future, explicitly configured social reporting adapters.

There are no installed adapters, credentials, network calls or posting workers.
Future imports must authorize and validate via services.record_metrics; provider
lifetime counters must be converted to daily increments before that call.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class DailyObservation:
    external_content_id: str
    date: date
    measures: dict[str, int]
    source: str


class SocialReportingProvider(Protocol):
    key: str

    def daily_observations(
        self, *, external_channel_id: str, start: date, end: date
    ) -> list[DailyObservation]: ...
