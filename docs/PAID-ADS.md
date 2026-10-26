# Paid Ads workspace — Phase 16

Staff enter or import daily advertising observations. The workspace reports
those records; it has no live connection to Google, Meta, LinkedIn or another
advertising provider. A new install contains no advertising performance data.

## Open the workspace

- Staff: **Delivery → Paid ads**, then select an assigned client.
- Client: **Paid advertising** at `/organization/area/paid_ads/`.
- Client access requires active membership in the selected organization, an
  active organization, and an active subscription mapped to `paid_ads`.
- Switching organizations changes both the Paid Ads entitlement and its data.

The staff workspace provides **Create campaign**, **Record a day**, **Import
CSV**, and **Manage goals**, according to the actor's permissions. Campaign
creation and status changes use the existing campaign engine and its permissions.
Statuses describe the agency's campaign record; changing them does not start or
stop advertising on an external platform.

## Data model

`DailyAdMetric` belongs to an organization and a shared `campaigns.Campaign` of
type `paid_ads`. Its unique key is **campaign + platform + date**. One campaign
can have observations from multiple platforms on the same day.

| Field | Meaning |
|---|---|
| `date` | Observation date, not import date; future observations are refused |
| `campaign` | This organization's shared Paid Ads campaign |
| `platform` | `google`, `meta`, `linkedin`, `other` |
| `spend`, `revenue` | Nonnegative decimal amounts, up to two decimal places |
| `impressions`, `clicks`, `leads`, `conversions` | Nonnegative whole-number counts |
| `currency` | Campaign currency copied when this daily key is first recorded |
| `source` | Required report/source description |
| `entry_method` | Manual or CSV |
| `recorded_by`, timestamps | Who last saved the observation and when |

Every metric is required. Zero means a measured zero. An absent date means no
observation is recorded; reports do not fill missing dates with fabricated zeroes.
There are no stored lifetime counters or stored ratio values.

Currency is preserved when an existing observation is corrected. A later change
to the campaign's currency affects new daily keys, not old observations. Reports
select one currency at a time and never add or convert different currencies.
The currency filter initially uses `SITE_DEFAULT_CURRENCY`.

## Reporting

Filters: inclusive start/end dates, platform, campaign and currency. The default
period is the last 30 days including today. A report can span up to 366 days;
older periods remain available by selecting their dates. Invalid filters return
an error instead of silently broadening the query.

KPI cards show **Ad Spend, ROAS, CPL, Leads, CTR, CPC, Conversions and Revenue**.
Tables group the same filtered observations by platform, campaign and day. The
daily table is paginated. Current campaign statuses are shown separately,
including campaigns with no observations.

| Derived metric | Calculation using period totals |
|---|---|
| ROAS | revenue / spend |
| CPL | spend / leads |
| CTR | clicks / impressions × 100 |
| CPC | spend / clicks |

Ratios are calculated after aggregation, never by averaging daily ratios. A
zero denominator yields an unavailable value (`—`). No observations produces
an empty state instead of KPI cards with invented zeroes. Revenue and conversion
attribution are inherited from the manually supplied source report; the platform
does not infer attribution or reconcile different providers' attribution windows.

## Manual entry and CSV import

First create a Paid Ads campaign in the shared campaign engine. Use **Record a
day** to enter the day's complete observations. Reusing a campaign/platform/date
corrects that record; it does not create a duplicate or add to its totals.

CSV requires UTF-8 (a BOM is accepted), at most 5 MB and 5,000 rows, and exactly
these columns (header order can vary):

```csv
date,campaign,platform,spend,impressions,clicks,leads,conversions,revenue
```

Dates use `YYYY-MM-DD`. `campaign` is a numeric ID; the import page lists available
Paid Ads campaign IDs and their currencies for the selected client. Platform
names are case-insensitive. Numeric fields use plain numbers without currency
symbols or thousands separators. The upload form records the source description.

Import behavior:

- All rows commit together or none do. Validation errors identify the row.
- Unknown/foreign campaigns, unsupported platforms, missing columns, malformed
  CSV, invalid numbers, duplicate daily keys within the file, and future dates
  are rejected.
- Reimporting a daily key replaces its values. It requires both create and edit
  permission, just like correcting through manual entry.
- Campaign rows are locked in stable order, and a database unique constraint
  protects the daily key. This serializes overlapping writes through the service.
- No emails, external API calls, or synthetic metrics are generated.

## Goals

`PaidAdsGoal` belongs to an organization, with a title, inclusive date range,
currency, target, optional platform/campaign, and active flag. The supported
measures are leads, conversions, revenue, minimum ROAS, maximum CPL and an ad
spend ceiling. Targets must be positive; count targets must be whole numbers.

Goals overlapping the report period are displayed. An active platform/campaign
filter displays goals for that exact scope, not a broader goal with a misleading
partial total. Each goal is evaluated against its **own full date range**, which
is printed next to it. All goal windows are read in one observation query rather
than one query per goal.

Spend and CPL use lower-is-better ceilings; other goals use higher-is-better
targets. No data or an undefined ratio is not success. Spending under a ceiling
is described as “within ceiling so far,” since the period may still be open.
Staff can edit or deactivate goals without deleting their history.

## Authorization and implementation

Staff reads require `paid_ads_view` and client assignment (or global client
access). Manual entry/import requires `paid_ads_create`; replacing an existing
observation also requires `paid_ads_edit`. Goal creation requires create access,
and goal changes require edit access. Services independently enforce the same
permissions and validate all linked campaigns against the organization and type.
Clients have read-only access; membership alone does not permit writes.

Files:

- `apps/paid_ads/models.py`: daily observations, goal schema and invariants.
- `services.py`, `policies.py`: validated writes and authorization.
- `selectors.py`: scoped reporting, weighted ratios and goal progress.
- `forms.py`, `importers.py`: manual input, filter validation and CSV handling.
- `views/admin.py`, `views/client.py`: staff and client workspaces.
- `templates/paid_ads/`: shared reporting tables and workspace templates.
- `migrations/0001_initial.py`: tables, indexes and constraints; no seed metrics.
- `tests/`: metric correctness, import rollback/idempotence, forms, permissions,
  tenant isolation and selected-organization entitlement.

The module reuses the staff and portal navigation registries, the design-system
components, and the existing campaign lifecycle. No new provider integration,
payment flow, background worker or parallel campaign model was introduced.

## Validation

At completion: **1,789 passed, 2 skipped** in the full test suite, with 53 Paid Ads
tests. Ruff and Django system/deployment checks pass. The deployment check retains
the project's intentional silenced mail check. Migration drift check reports no
changes; the new migration was applied to the local development database. Tailwind
CSS was rebuilt.

The shared tenant inventory was extended. The existing campaign registry test
was isolated so its replacement SEO registration cannot leak into later tests;
the existing SEO empty-state assertion now normalizes whitespace. Three existing
SEO test lint findings were corrected. Application authorization issues recorded
in the earlier project study outside the Paid Ads paths were not addressed here.

HTML rendering is exercised with Django's test client. Browser-based visual and
keyboard interaction checks were not run in this environment.
