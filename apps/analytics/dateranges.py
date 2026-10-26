"""The one date-range picker every analytics page shares.

Section 35 of the brief asks for nine presets and proper timezone
handling, used identically by the admin's business analytics, the
agency website page, and every client-facing report. Written once, here,
because a second implementation would inevitably disagree with this one
about what "this month" means at 23:58 on the last day of it.

`resolve(key, *, today=None)` is the one function everything calls. It
returns a `DateRange` — always a closed `[start, end]` pair of `date`
objects in the **server's local date**, via `timezone.localdate()`
rather than `date.today()`, so a deployment in a different timezone to
UTC still draws the boundary at the right midnight.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

TODAY = "today"
YESTERDAY = "yesterday"
LAST_7_DAYS = "last_7_days"
LAST_30_DAYS = "last_30_days"
THIS_MONTH = "this_month"
PREVIOUS_MONTH = "previous_month"
LAST_3_MONTHS = "last_3_months"
LAST_12_MONTHS = "last_12_months"
CAMPAIGN_LIFETIME = "campaign_lifetime"
CUSTOM = "custom"

#: Display order and labels, for the picker. `CUSTOM` is listed last and
#: handled specially by the view that renders it — see
#: `apps.analytics.forms.DateRangeForm`. `CAMPAIGN_LIFETIME` only means
#: anything where a form is scoped to one campaign — see
#: `resolve_for_campaign` — so a general-purpose picker omits it.
PRESET_CHOICES = [
    (TODAY, _("Today")),
    (YESTERDAY, _("Yesterday")),
    (LAST_7_DAYS, _("Last 7 days")),
    (LAST_30_DAYS, _("Last 30 days")),
    (THIS_MONTH, _("This month")),
    (PREVIOUS_MONTH, _("Previous month")),
    (LAST_3_MONTHS, _("Last 3 months")),
    (LAST_12_MONTHS, _("Last 12 months")),
    (CUSTOM, _("Custom")),
]

#: The picker for a page scoped to one campaign — adds "Campaign
#: lifetime" after the calendar presets, matching section 20's own list.
CAMPAIGN_PRESET_CHOICES = [
    *PRESET_CHOICES[:-1],
    (CAMPAIGN_LIFETIME, _("Campaign lifetime")),
    PRESET_CHOICES[-1],
]

DEFAULT_PRESET = LAST_30_DAYS


@dataclass(frozen=True, slots=True)
class DateRange:
    """A closed, inclusive range: both `start` and `end` are included."""

    key: str
    start: date
    end: date
    label: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def previous(self) -> DateRange:
        """The immediately preceding period of equal length.

        What "vs previous period" (section 36) compares against. A
        7-day range ending today compares against the 7 days before
        that — not against the same weekday last month, which would be a
        different and more surprising comparison to draw without asking.
        """
        span = self.days
        end = self.start - timedelta(days=1)
        start = end - timedelta(days=span - 1)
        return DateRange(key="previous", start=start, end=end, label="Previous period")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def resolve(key: str, *, today: date | None = None,
           custom_start: date | None = None,
           custom_end: date | None = None) -> DateRange:
    """The concrete `[start, end]` for one preset key.

    `today` is injectable for tests; every caller in production code
    should leave it as `None` and get `timezone.localdate()`.
    """
    today = today or timezone.localdate()
    labels = dict(PRESET_CHOICES)

    if key == TODAY:
        return DateRange(key, today, today, labels[TODAY])
    if key == YESTERDAY:
        day = today - timedelta(days=1)
        return DateRange(key, day, day, labels[YESTERDAY])
    if key == LAST_7_DAYS:
        return DateRange(key, today - timedelta(days=6), today, labels[LAST_7_DAYS])
    if key == LAST_30_DAYS:
        return DateRange(key, today - timedelta(days=29), today, labels[LAST_30_DAYS])
    if key == THIS_MONTH:
        start, _end = _month_bounds(today.year, today.month)
        return DateRange(key, start, today, labels[THIS_MONTH])
    if key == PREVIOUS_MONTH:
        first_of_this_month = today.replace(day=1)
        last_of_previous = first_of_this_month - timedelta(days=1)
        start, end = _month_bounds(last_of_previous.year, last_of_previous.month)
        return DateRange(key, start, end, labels[PREVIOUS_MONTH])
    if key == LAST_3_MONTHS:
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        start = (start - timedelta(days=1)).replace(day=1)
        return DateRange(key, start, today, labels[LAST_3_MONTHS])
    if key == LAST_12_MONTHS:
        try:
            start = today.replace(year=today.year - 1)
        except ValueError:  # 29 Feb with no leap year to land on
            start = today.replace(year=today.year - 1, day=28)
        return DateRange(key, start, today, labels[LAST_12_MONTHS])
    if key == CUSTOM and custom_start and custom_end:
        start, end = min(custom_start, custom_end), max(custom_start, custom_end)
        return DateRange(CUSTOM, start, end, labels[CUSTOM])

    # An unknown or incomplete custom range falls back to the default
    # rather than raising — a date picker is exactly the kind of input a
    # person fat-fingers, and a report that still renders with a sane
    # range beats a 500 over a date field.
    return resolve(DEFAULT_PRESET, today=today)


def resolve_for_campaign(key: str, campaign, *, today: date | None = None,
                         custom_start: date | None = None,
                         custom_end: date | None = None) -> DateRange:
    """Like `resolve`, plus the one preset only a campaign's own page
    offers — "the whole time this has been running," end to end.

    Section 20 calls this out by name because the other eight presets
    all answer "how is this doing lately," and a campaign's own page
    needs to answer "how has this done, full stop" at least as often.
    """
    today = today or timezone.localdate()
    if key == CAMPAIGN_LIFETIME:
        start = campaign.starts_on or campaign.created_at.date()
        end = campaign.ends_on or today
        if end < start:
            end = start
        label = dict(CAMPAIGN_PRESET_CHOICES)[CAMPAIGN_LIFETIME]
        return DateRange(CAMPAIGN_LIFETIME, start, end, label)
    return resolve(key, today=today, custom_start=custom_start, custom_end=custom_end)
