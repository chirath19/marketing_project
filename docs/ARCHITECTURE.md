# Heliograph Platform — Architecture Plan

Status: **plan only, nothing built yet.** Date: 2026-10-03.

---

## 1. What I understand

A production-grade **digital marketing agency platform** — public marketing site + CMS +
service catalogue + quote/purchase workflow + client portal + staff/admin back office —
built as a **modular monolith** on Django / DRF / PostgreSQL, server-rendered with Django
Templates + Tailwind + HTMX + Alpine, Cloudinary-compatible media, deployable to Railway.

Hard constraints for v1:

- **No Redis, no Celery, no outbound email / SMS / WhatsApp / any external messaging provider.**
- Every contact form, quote request, enquiry, client message, approval request and system
  alert is **persisted in PostgreSQL** and surfaced in an **in-app Inbox + Notification Center**.
- The messaging layer must be **pluggable**: adding a real provider later must be a new adapter
  + config, not a rewrite.
- Business logic lives in **service / selector / policy layers**, not in views, serializers,
  templates, `Model.save()` or signals.
- Security = **RBAC + object-level permissions + organization isolation**, enforced
  server-side on every protected object. Hidden UI is never a control.

### Brand (from the build brief)

| Token | Hex | Use |
|---|---|---|
| Deep Navy | `#111C38` | Primary, wordmark |
| Midnight | `#233457` | Cards, sections |
| Solar Gold | `#E4A33C` | Accent, "the light" |
| Steel | `#6E7B96` | Secondary text |
| Mist | `#EEF1F6` | Cool background |
| White | `#FFFFFF` | Space |

Product name in the references: **Heliograph** (`hello@heliograph.agency`). Treated as a
`SiteSettings` value, never hardcoded.

---

## 2. What the PDFs actually specify

Five distinct references (`...Claude.pdf` duplicates `...Claude Paid ads.pdf`).

**`Website Build Brief.pdf`** — pages required: Admin panel, Service page, Contact, Blog,
Client dashboard, Mailbox, Consent tool, Privacy policy. Front end: responsive brand theme,
reusable parts (catalog cards, leads form, dashboard widgets), SEO-ready blog (meta tags,
sitemap, fast loading), **dataLayer events on key actions (form submit, package click)**.
Back end: role-based login for admin and client, DB for leads/packages/posts/clients, leads
form saved to DB **and the mailbox**, client dashboard fed by ad-platform and lead data.
Tracking: **GTM on every page, RudderStack for event collection, GA4 for analytics, consent
tool blocks all three until the visitor agrees, privacy policy names each tool.**
Dashboard headline KPIs: Leads, Ad spend, Revenue, Cost per lead — for a selected date range.

**`...overview.pdf`** (client dashboard home) — top nav: Overview / Campaigns / SEO /
Paid ads / Social media / Email, with an unread count on Overview. Period selector
("Last 12 months"). Four KPI tiles with delta vs last period. A leads-by-channel trend chart.
**Progress to monthly goals** bars per service (`412 of 450`). **Waiting for your approval**
list with inline Approve. **Recent activity** feed, each item tagged by service + relative time.

**`...Catalog.pdf`** (public) — hero + "Browse the catalog" / "Talk to us". Category filter
tabs: All / Search / Paid / Social / Email / Analytics. Service cards: category badge, name,
description, expandable **"What is included"**, price with billing period (`$2,400 per month`,
`$1,500 one time`), and **"Add to quote"**. Twelve seed services across the five categories.
Then a **"Request your quote"** form: name, work email, website, goals →
"we confirm scope and cost within one working day". Cookie banner (Allow / No thanks) and a
footer "Tracking" link.

**`...Campaigns.pdf`** — table: Campaign | Service | Status | Spend | Result, with status
filter tabs **All / Live / Paused / Planned / Done**. `Result` is a short human-written
outcome string ("61 links won", "LCP 4.1s → 1.9s", "Starts Jun 2", "Waiting on your approval").

**`...Paid ads.pdf`** — per-module page pattern: 3 module KPIs (Ad spend, ROAS, CPL) with
deltas, a trend chart, a monthly goal bar, a **"Next review call: Thursday, 10:00 — message
Amara from the Heliograph team"** block (→ client↔staff assignment + in-app messaging), then
the filtered campaign table scoped to that module with a module-specific `Type` column
(Google / Meta / LinkedIn).

**Design conclusions carried into the architecture:** every module page is the same composed
shell (KPI row → chart → goal → approvals/next-step → campaign table), so it becomes **one
reusable module-dashboard template** driven by a module registry. SEO / Social / Email pages
weren't supplied; I will build them on that pattern and flag them for review.

---

## 3. Technology decisions

| Area | Decision |
|---|---|
| Runtime | Python 3.14, Django (version to pin in P0 — see risk below) |
| API | Django REST Framework — internal/secondary; the dashboards are server-rendered |
| DB | PostgreSQL 17 (Docker Compose locally; Railway Postgres in prod) |
| Templates | Django Templates + component partials via inclusion tags |
| Interactivity | HTMX for partial updates; Alpine.js only for local UI state |
| CSS | Tailwind (standalone CLI build → `static/dist/app.css`), brand tokens in config |
| Charts | Server-prepared JSON + a lightweight canvas chart lib, loaded only on chart pages |
| Media | `MediaAsset` model over Django `STORAGES`; local in dev, Cloudinary in prod |
| Static | WhiteNoise, hashed manifest |
| Cache | Database-backed cache table (`createcachetable`) + per-request memoization. **No Redis.** |
| Background work | None in v1. Deferred work goes to an **outbox table** drained by an idempotent management command (Railway cron later). No Celery. |
| Config | Environment variables via `django-environ`; `DATABASE_URL` via `dj-database-url` |
| Tests | pytest + pytest-django + factory_boy; `assertNumQueries` on list views |
| Server | Gunicorn behind Railway |

**Risk to settle in P0:** the venv currently has **Django 6.1.1 on Python 3.14**, which is not
an LTS. For a platform that has to be maintained, I'd pin **the current LTS** unless you want
the newest. Either way P0 must verify DRF, psycopg 3, Pillow and the Cloudinary SDK all have
working wheels on this Python/Django pair before any app code is written — a dependency that
can't install later is expensive. I'll report the compatibility matrix and recommend a pin.

---

## 4. Repository layout

```
config/
  settings/{base,dev,prod,test}.py
  urls.py  asgi.py  wsgi.py
apps/
  core/            base models, event bus, module registry, SystemSetting, UI tags, mixins
  accounts/        custom User, auth flows, profiles
  organizations/   client organizations + memberships
  staff/           staff profiles, teams, client assignments
  permissions/     roles, permission registry, per-user overrides, policy engine
  cms/             pages, blocks, blog, case studies, testimonials, navigation, redirects
  catalog/         categories, services, packages, pricing, inclusions, FAQs
  leads/           contact submissions, enquiries, leads, attribution
  quotes/          quote builder (cart), quote requests, quote lines, proposals
  subscriptions/   service requests, orders, subscriptions, entitlements, invoices (manual)
  campaigns/       the delivery spine: Campaign, status, spend, result, milestones
  seo/             SEO module models + dashboard
  paid_ads/        Paid ads module models + dashboard
  social/          Social module models + dashboard
  email_marketing/ Email marketing module models + dashboard (work FOR clients, sends nothing)
  analytics/       metric snapshots, goals, period comparison, reports, CSV import
  approvals/       generic approval requests + decisions
  messaging/       threads, participants, messages, attachments (in-app only)
  notifications/   notifications, preferences, Notification Center, outbox + channel registry
  media/           MediaAsset, transformations, responsive image tags
  tracking/        consent records, consent categories, tag/script config, dataLayer events
  integrations/    provider registry, credentials, sync runs (no live providers in v1)
  audit/           immutable audit log
templates/
  base/  components/  public/  dashboard/  staff/  emails_preview/
static/src/  static/dist/
docs/  tests/  scripts/
```

Deviations from your suggested list, with reason:

- **`quotes` split out of `leads`.** The catalog PDF shows a multi-service quote builder with
  line items that becomes an order — that's a different lifecycle from a contact enquiry.
- **`apps/` package prefix.** Keeps 21 domains out of the repo root and makes import paths
  unambiguous.
- Everything else matches your proposed domains.

---

## 5. Layering — the rule that keeps logic out of views

Each domain app exposes:

```
models.py / models/     persistence only; no business rules in save()
selectors.py            all reads; every queryset here is select_related/prefetch_related-complete
services.py             all writes; transactional; the only place state changes
policies.py             "can this actor do this to this object?" — pure functions
events.py               domain events this app emits
forms.py                input validation only
views/                  thin: authorize → call selector/service → render
api/                    serializers = shape only; viewsets call the same services
```

Enforced conventions:

- Views and serializers **may not** import another app's models directly — only its selectors
  and services. A test walks the import graph and fails the build on violations.
- `Model.save()` holds no business rules. Signals are used only for infrastructure concerns.
- Cross-domain reactions go through a **synchronous in-process event bus** in `core`,
  dispatched inside `transaction.on_commit`. Example: `QuoteRequested` → notifications creates
  an inbox item, audit writes a log entry — without `quotes` importing either app.
- Multi-step workflows get an explicit **state machine** in the service layer with allowed
  transitions declared as data, so illegal transitions raise rather than silently pass.

---

## 6. Identity, tenancy and security

**Users.** Custom `accounts.User` (email login) with `user_type ∈ {SUPER_ADMIN, STAFF, CLIENT}`.
A client user belongs to one or more `Organization`s via `OrganizationMembership`
(`OWNER / ADMIN / MEMBER / VIEWER`). Staff get a `StaffProfile`; `ClientAssignment` links a
staff member to an organization with a role (account manager, SEO specialist, …) — this is
what powers "message Amara from the Heliograph team".

**Permissions resolution**, single implementation, used by web views, DRF and templates:

```
deny override  >  grant override  >  role permissions  >  default deny
```

`permissions` holds a declarative codename registry (`campaigns.approve`, `leads.export`, …),
`Role`, `RolePermission`, `UserPermissionOverride`. Resolved once per request and memoized;
a `permissions_version` counter on the user invalidates it. No Redis needed.

**Organization isolation.** A `OrganizationOwnedModel` base (indexed `organization` FK) plus an
`OrgScopedQuerySet.visible_to(user)` manager method. Client views **never** accept an
organization id from the client — it is resolved server-side from the session. Staff access to
an organization requires an active `ClientAssignment` (or a global override). A base test case
asserts, for every tenant model, that org A cannot read, list, update or delete org B's rows;
new models are added to that matrix or the test fails.

**Object-level checks** live in `policies.py` and are invoked *inside services*, so the rule
holds no matter which entry point (web, API, admin action, management command) reaches it.
Template-level `{% if can %}` is cosmetic only.

**Auth without outbound email** — a real consequence of the no-email rule, so it's designed for,
not patched later: self-registration creates a pending account and an inbox item for staff;
verification and password resets are handled in-app (staff-issued, single-use, expiring tokens
recorded as `PasswordResetRequest` rows and surfaced in the Inbox). Django's mailer stays on a
console/locmem backend so nothing can leak out. When a provider is added, the same tokens are
simply delivered by it instead.

---

## 7. Messaging and notifications — pluggable from day one

```
Notification(recipient, org, kind, title, body, link, read_at, severity)
Thread / ThreadParticipant / Message / MessageAttachment     in-app conversations
OutboundMessage(channel, payload, status, attempts, last_error, dedupe_key)   the outbox
```

`notifications.channels` is a **registry of channel adapters** behind one interface
(`can_handle`, `send`). v1 registers exactly one: `InAppChannel`, which writes a
`Notification` row — the Inbox and Notification Center read from those tables. Adding email,
SMS or WhatsApp later = write an adapter, register it, enable it in `integrations` settings.
No core change.

The outbox exists from the start (written in the same transaction as the business change, so
nothing is lost) but is drained synchronously by the in-app channel. A `drain_outbox`
management command is the seam where a worker or Railway cron plugs in later.

Every public submission path — contact form, enquiry, quote request — writes its domain row,
emits an event, and lands in the staff Inbox. That satisfies the brief's "leads form saved to
the database **and the mailbox**".

---

## 8. Catalogue → quote → subscription → dashboard

```
ServiceCategory → Service → ServiceTier/Package → PricingOption(one_time|monthly) → Inclusion
Quote (draft cart, session- or account-bound) → QuoteLine → QuoteRequest (submitted)
ServiceRequest → Order → Subscription → SubscriptionItem → Entitlement
```

The catalog page's "Add to quote" builds a `Quote` for anonymous visitors (session-keyed) and
converts on submit; the quote request captures name, work email, website and goals exactly as
the PDF shows, then appears in the staff Inbox with a one-working-day SLA field.

**Entitlements drive the dynamic client dashboard.** Each delivery module registers itself in
`core.registry` with a key, label, nav order, icon, KPI provider and `is_enabled(organization)`
backed by active subscription items. The dashboard nav, the module pages and the API all read
that registry — so a client who hasn't bought Social simply has no Social nav item, no Social
route (403 server-side, not a hidden link) and no Social KPIs.

---

## 9. Delivery, approvals and analytics

`campaigns.Campaign` is the spine: organization, service/module, name, status
(`PLANNED / LIVE / PAUSED / DONE`), start/end, budget, spend, owner staff, and the short
`result_summary` string the PDFs display. Each module app attaches its own detail models and
module-specific fields (Paid ads: platform `Google|Meta|LinkedIn`, ROAS; SEO: keywords,
backlinks, Core Web Vitals; Social: channels, posts; Email: flows, sends, conversion rate).

`approvals.ApprovalRequest` is generic (`GenericForeignKey` + `Approvable` mixin) so any object
— an ad creative, a newsletter draft, a creator brief — can be sent for client approval. It
renders both in the Overview "Waiting for your approval" list and inline on module pages, and
decisions are recorded with actor, timestamp and comment.

`analytics` holds a narrow, indexed `MetricSnapshot(organization, module, campaign, metric_key,
period_start, period_granularity, value)` plus `Goal(organization, module, metric, target,
period)` for the "412 of 450" bars, and a `PeriodComparison` selector that computes the
"+9% vs last period" deltas from one indexed query per tile. Data entry in v1 is manual +
CSV import; `integrations` later writes to the same table, so no dashboard code changes.
"Revenue from closed leads" comes from `leads` (lead value + closed status), not an ad platform.

---

## 10. Tracking and consent

The brief is explicit: **GTM, RudderStack and GA4 must stay blocked until the visitor agrees.**

`tracking` models consent categories (necessary / analytics / marketing), `ConsentRecord`
(anonymous id or user, categories granted, policy version, IP, user agent, timestamp — the
auditable proof), and `TrackingTag` (provider, container/write key, placement, required
consent category, enabled). The base template renders **no third-party tag** server-side unless
the request's consent cookie grants the matching category; the banner (Alpine, Allow / No
thanks) writes the record via HTMX and only then injects tags. A `dataLayer` helper emits the
brief's key events (`form_submit`, `package_click`, `quote_submit`). The privacy policy page is
generated from the enabled `TrackingTag` rows so it always names each tool in use.

---

## 11. Frontend design system

One Tailwind theme, brand tokens only — no raw hex in templates. Three template roots
(`public/`, `dashboard/`, `staff/`) over one shared `components/` library:

> button · link · badge · card · stat-tile · delta · progress-bar · table · table-toolbar ·
> filter-tabs · pagination · form-field · select · modal · drawer · dropdown · tabs · avatar ·
> alert · empty-state · skeleton · breadcrumb · nav-item · chart-frame · activity-item ·
> approval-row · service-card · period-picker

Each is an inclusion tag in `core/templatetags/ui.py` with typed, documented arguments, plus a
`/styleguide/` page (staff-only) rendering every component in every state — that page is the
responsive and dark-surface check each phase.

HTMX handles: inbox and notification polling, table filter/sort/paginate, modals, approve /
reject, inline form validation. Alpine handles only local UI state (dropdown open, tab
selected, banner dismissed). Public pages ship near-zero JS; chart JS loads only where a chart
renders.

---

## 12. Performance budget

Indexes declared with each model (every FK, every status/date column used in a filter,
composite `(organization, created_at)` on all list surfaces, and
`(organization, module, metric_key, period_start)` on `MetricSnapshot`). All reads go through
selectors that are `select_related`/`prefetch_related`-complete; every list view has a
query-count test so an N+1 fails CI rather than production. Pagination everywhere, keyset
pagination on the big tables. `only()`/`defer()` on wide rows. Responsive images with
`srcset` + lazy loading through the media tag. DB cache for navigation and site settings.

---

## 13. Deployment

Railway: `railway.toml` + `Procfile`, Gunicorn, WhiteNoise, `DATABASE_URL`, release command
running `migrate` and `collectstatic`, `/healthz` endpoint, `DEBUG=False`, `ALLOWED_HOSTS` and
`CSRF_TRUSTED_ORIGINS` from env, full `SECURE_*` / HSTS / secure-cookie set, Cloudinary creds
by env. Secrets never in the repo; the current `django-insecure-` key is replaced in P0.
Local parity via Docker Compose Postgres (there's no local `psql` on this machine, so this is
required before P1).

---

## 14. Definition of done, per phase

Your ten working rules run at the end of every phase, and nothing is reported complete
without: migrations created and applied, `manage.py check --deploy` clean, tests written and
passing (service + policy + view + query-count), the **org-isolation matrix** extended to any
new tenant model, responsive check at 375 / 768 / 1280 on the styleguide and the new screens,
a list of files changed, and a list of what is still outstanding.

---

## 15. Phase plan

| Phase | Scope | Exit criteria |
|---|---|---|
| **P0 Foundation** | Dependency compatibility matrix + version pins, settings split, Postgres via Compose, `core` (base models, event bus, registry, SystemSetting, UI tags), Tailwind pipeline + brand tokens, base layouts, first components, styleguide page, pytest harness, git init | `check --deploy` clean, styleguide renders, CI-equivalent make targets pass |
| **P1 Identity** | `accounts`, `organizations`, `staff`, `permissions`, auth flows (in-app verification/reset), three dashboard shells with real nav gating | Permission matrix + org-isolation tests green |
| **P2 Public + CMS + Catalog + Leads** | `cms`, `catalog`, `media`, public site (home, services, service detail, blog, contact, privacy), `leads`, `quotes` quote builder, `messaging` + `notifications` Inbox and Notification Center | Quote and contact submissions land in DB + Inbox; SEO meta + sitemap present |
| **P3 Purchasing** | `subscriptions`, service requests, entitlements, module registry wiring, dynamic client dashboard Overview with KPI tiles, goals and activity feed | A client sees exactly their purchased modules, verified server-side |
| **P4 Delivery** | `campaigns` + `seo` + `paid_ads` + `social` + `email_marketing` module pages on the shared pattern, `approvals` | Campaign table, module KPIs, goal bars and approve flow working per the PDFs |
| **P5 Measurement & governance** | `analytics` (snapshots, comparisons, CSV import, reports), `tracking` consent + GTM/RudderStack/GA4 gating, `audit`, system + `integrations` settings | Consent provably blocks all three tags pre-consent; audit covers every service write |
| **P6 Hardening & launch** | Query-count and index pass, a11y and responsive pass, seed/demo data, Railway deploy, runbook | Deployed, documented, performance budget met |

---

## 16. Assumptions, and what I need from you

Assumed (tell me if wrong — each is cheap now, expensive in P3):

1. **One agency, many client organizations** — not a multi-agency SaaS where agencies sign up.
2. **No payment gateway in v1.** Quotes and subscriptions are confirmed by staff; invoices are
   records, not charges. The PDFs show "we confirm scope and cost within one working day",
   which reads as manual confirmation.
3. **USD and a single currency**, configurable in settings — the references all show `$`.
4. DRF is for future/internal consumers; no public API contract is being promised in v1.
5. SEO / Social media / Email module pages follow the Paid ads layout, since they weren't
   supplied as mockups.

Open questions:

- **Django version pin** — newest, or LTS? (My lean: LTS, for a platform you'll maintain.)
- **Payments** — confirm none in v1, or name the gateway so the data model leaves room.
- **Who enters metrics in v1** — staff via forms, CSV import, or both? I've planned both.
- **Blog authorship** — staff-only, or client-visible contributors?
- Are there mockups for SEO / Social / Email module pages, or should I derive them?

Nothing here is built yet. On your go-ahead I'll start **P0** and report against the ten rules.
