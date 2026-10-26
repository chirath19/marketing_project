"""Bringing keyword positions in from a file.

Rank tracking lives in tools the agency already pays for, and those tools
export CSV. So the import path is a file upload, not an API client:
nothing here reaches out to anything, and every figure can be traced to
the file a person chose to upload.

The importer is deliberately forgiving about *shape* and strict about
*meaning*. Column names vary between tools, so several spellings are
accepted; a position that is not a number is refused rather than guessed
at, because a wrong rank silently stored is worse than a row rejected.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.seo import policies
from apps.seo.models import Keyword, KeywordRanking

#: Column names the common rank trackers use, lowercased. The first
#: match wins, so a file with both "keyword" and "query" is read the way
#: its author most likely meant.
TERM_COLUMNS = ("keyword", "query", "term", "search term", "keywords")
POSITION_COLUMNS = ("position", "rank", "current position", "avg. position",
                    "average position", "pos")
DATE_COLUMNS = ("date", "recorded", "recorded_on", "day")
URL_COLUMNS = ("url", "landing page", "target url", "page")
VOLUME_COLUMNS = ("volume", "search volume", "monthly searches", "impressions")

MAX_ROWS = 5000

#: Date formats seen in exports, most specific first.
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d")


@dataclass(slots=True)
class ImportResult:
    """What the import did, in terms a person can act on."""

    keywords_created: int = 0
    positions_recorded: int = 0
    rows_skipped: int = 0
    #: Why rows were skipped, so somebody can fix the file rather than
    #: wonder. Capped, because a wholly wrong file would otherwise
    #: produce five thousand identical complaints.
    problems: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        self.rows_skipped += 1
        if len(self.problems) < 10:
            self.problems.append(message)

    @property
    def did_anything(self) -> bool:
        return bool(self.keywords_created or self.positions_recorded)


def _pick(row: dict, candidates: tuple[str, ...]) -> str:
    """The first column from `candidates` this row actually has."""
    for name in candidates:
        if name in row and (row[name] or "").strip():
            return row[name].strip()
    return ""


def _parse_date(raw: str, *, default: date) -> date | None:
    if not raw:
        return default
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_position(raw: str) -> tuple[int | None, bool]:
    """A position, and whether the value was usable.

    Returns ``(None, True)`` for a blank or an explicit "not ranked",
    which is a real observation and different from a parse failure.
    """
    if not raw:
        return None, True

    cleaned = raw.replace(">", "").replace("+", "").strip()
    if cleaned.lower() in {"-", "n/a", "na", "not ranked", "none", "100+"}:
        return None, True

    try:
        value = int(float(cleaned))
    except ValueError:
        return None, False

    if value < 1:
        return None, False
    # Beyond the top 200 is "not ranked" as far as this platform is
    # concerned, and the model's validator agrees.
    return (value if value <= 200 else None), True


@transaction.atomic
def import_keyword_positions(*, organization, actor, file_obj,  # noqa: ANN001
                             source: str = "",
                             recorded_on: date | None = None) -> ImportResult:
    """Read keyword positions from an uploaded CSV.

    Keywords not already tracked for this client are created, so one
    file can both start tracking a set of terms and record where they
    sat. Existing keywords keep their settings — an import updates
    positions, never priorities somebody chose by hand.
    """
    if not policies.can_create_seo(actor, organization):
        raise PermissionDenied("You may not import SEO data for this client.")

    result = ImportResult()
    default_date = recorded_on or timezone.localdate()

    raw = file_obj.read()
    if isinstance(raw, bytes):
        # Exports from spreadsheet tools are frequently UTF-8 with a BOM,
        # which would otherwise become part of the first column's name.
        raw = raw.decode("utf-8-sig", errors="replace")

    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        result.note("The file has no header row.")
        return result

    # Normalised once rather than per row.
    reader.fieldnames = [(name or "").strip().lower()
                         for name in reader.fieldnames]

    if not any(name in reader.fieldnames for name in TERM_COLUMNS):
        result.note(
            "No keyword column found. Expected one of: "
            + ", ".join(TERM_COLUMNS) + "."
        )
        return result

    seen: dict[str, Keyword] = {}

    for number, row in enumerate(reader, start=2):
        if number - 1 > MAX_ROWS:
            result.note(f"Stopped after {MAX_ROWS} rows.")
            break

        row = {(key or "").strip().lower(): (value or "")
               for key, value in row.items()}

        term = _pick(row, TERM_COLUMNS)
        if not term:
            result.note(f"Row {number}: no keyword.")
            continue
        term = term[:200]

        position, usable = _parse_position(_pick(row, POSITION_COLUMNS))
        if not usable:
            result.note(f"Row {number}: “{_pick(row, POSITION_COLUMNS)}” is "
                        "not a position.")
            continue

        observed = _parse_date(_pick(row, DATE_COLUMNS), default=default_date)
        if observed is None:
            result.note(f"Row {number}: could not read the date.")
            continue

        keyword = seen.get(term.lower())
        if keyword is None:
            keyword, created = Keyword.objects.get_or_create(
                organization=organization, term=term,
                defaults={
                    "target_url": _pick(row, URL_COLUMNS)[:300],
                    "search_volume": _volume(row),
                },
            )
            seen[term.lower()] = keyword
            if created:
                result.keywords_created += 1

        KeywordRanking.objects.update_or_create(
            keyword=keyword, recorded_on=observed,
            defaults={"position": position, "source": source[:120] or "CSV import"},
        )
        result.positions_recorded += 1

    return result


def _volume(row: dict) -> int | None:
    raw = _pick(row, VOLUME_COLUMNS).replace(",", "")
    try:
        return int(float(raw)) if raw else None
    except ValueError:
        return None
