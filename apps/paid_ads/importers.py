"""Bounded, atomic CSV imports. Reimporting a daily key replaces it, never adds to it."""

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.paid_ads import policies, selectors, services
from apps.paid_ads.models import OPTIONAL_MEASURES, REQUIRED_MEASURES, Platform

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
#: Every export this importer has ever accepted has exactly these
#: columns — kept mandatory so an old, working template never breaks.
COLUMNS = ("date", "campaign", "platform", *REQUIRED_MEASURES)
#: May additionally be present; a column header outside this combined
#: set is still rejected as a typo rather than silently ignored.
ALL_COLUMNS = (*COLUMNS, *OPTIONAL_MEASURES)


@transaction.atomic
def import_metrics(*, actor, organization, file_obj, source):
    if not policies.can_write(actor, organization):
        raise PermissionDenied("You may not import advertising performance for this client.")
    raw = file_obj.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError("Upload a CSV no larger than 5 MB.")
    try:
        content = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    except UnicodeDecodeError as exc:
        raise ValidationError("Save the CSV as UTF-8.") from exc
    reader = csv.DictReader(io.StringIO(content), strict=True)
    try:
        headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
        extra_measures = [name for name in headers if name in OPTIONAL_MEASURES]
        if (len(headers) != len(set(headers))
                or not set(COLUMNS) <= set(headers)
                or not set(headers) <= set(ALL_COLUMNS)):
            raise ValidationError(
                "Use these CSV columns: " + ", ".join(COLUMNS)
                + ". May also include: " + ", ".join(OPTIONAL_MEASURES) + "."
            )
        reader.fieldnames = headers
        campaigns = {c.pk: c for c in selectors.campaigns_for(actor, organization)}
        staged, seen = [], set()
        for number, row in enumerate(reader, start=2):
            if number - 1 > MAX_ROWS:
                raise ValidationError(f"Use no more than {MAX_ROWS} rows per import.")
            if None in row or any(v is None for v in row.values()):
                raise ValidationError(
                    f"Row {number}: the number of columns does not match the header."
                )
            try:
                campaign = campaigns.get(int(row["campaign"].strip()))
                if campaign is None:
                    raise ValueError("Choose a Paid Ads campaign ID from this workspace.")
                observed = date.fromisoformat(row["date"].strip())
                platform = row["platform"].strip().lower()
                if platform not in Platform.values:
                    raise ValueError(
                        f"Platform must be one of: {', '.join(Platform.values)}."
                    )
                values = {}
                for name in (*REQUIRED_MEASURES, *extra_measures):
                    raw_value = row[name].strip()
                    if not raw_value and name in extra_measures:
                        continue  # left genuinely unreported, not zero
                    value = Decimal(raw_value)
                    if not value.is_finite() or value < 0:
                        raise ValueError(f"{name} must be a finite, nonnegative number.")
                    if name not in {"spend", "revenue"}:
                        if value != value.to_integral_value() or value > 9223372036854775807:
                            raise ValueError(f"{name} must be a nonnegative whole number in range.")
                        value = int(value)
                    values[name] = value
                key = (campaign.pk, platform, observed)
                if key in seen:
                    raise ValueError("Duplicate campaign/platform/date in this file.")
                seen.add(key)
                staged.append((number, campaign, observed, platform, values))
            except (ValueError, InvalidOperation) as exc:
                raise ValidationError(f"Row {number}: {exc}") from exc
    except csv.Error as exc:
        raise ValidationError("The CSV could not be read. Check its quoting and columns.") from exc
    if not staged:
        raise ValidationError("The file contains no observations.")
    # Stable parent lock order avoids deadlocks between overlapping imports.
    for number, campaign, observed, platform, values in sorted(staged, key=lambda row: row[1].pk):
        try:
            services.record_metrics(
                organization=organization,
                actor=actor,
                campaign=campaign,
                date=observed,
                platform=platform,
                source=source,
                entry_method="csv",
                **values,
            )
        except ValidationError as exc:
            raise ValidationError(f"Row {number}: {' '.join(exc.messages)}") from exc
    return len(staged)
