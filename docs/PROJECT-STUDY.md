# Project study — 2026-10-07

For the current dashboard organization, see [WORKFLOW-REDESIGN.md](WORKFLOW-REDESIGN.md).

Historical snapshot taken before Phase 16. Paid Ads has since been implemented;
see [PAID-ADS.md](PAID-ADS.md) for its behavior and the updated validation results.

This is a code-based map of the current Heliograph project, with findings verified during the study. It supplements the original architecture plan, which describes several features that are not implemented yet. Application behavior was not changed during this review.

The review covered the 21 application domains, configuration and routing, model relationships and migrations, services/selectors/policies, public and staff workflows, portal entitlements, templates and UI infrastructure, tests, and deployment files. There are 147 HTML templates, 47 test files, and 33 numbered migrations. Installed dependencies and generated/vendor assets were treated as dependencies rather than application source. Browser interaction, production deployment, and live Cloudinary operations were not exercised.

**Product and architecture**

Heliograph supports one marketing agency serving multiple client organizations. Its three main surfaces are the public marketing website, the staff back office, and the client portal. Django's own admin is a separate development/administration surface.

The repository pins Django 6.1.1, DRF 3.18.1, and Tailwind 4.3.3. The local interpreter reports Python 3.14.6. PostgreSQL is the application and test database; Compose specifies PostgreSQL 17. Pages are rendered by Django templates. HTMX provides request enhancements, while Alpine and `static/js/ui.js` manage local interaction. Node is used to build CSS.

The intended layering is:

```text
Request → URL/view + authorization → selectors for reads
                                 → services + policies for writes
                                 → models/database
                                 → templates/shared components
```

Services commonly use `transaction.atomic`, validate transitions, append history, and publish domain events. The implementation also contains direct calls between domains' services and some imports of their models. It is not exclusively event-driven.

`core.events` dispatches events after transaction commit and logs/swallow handler exceptions. No production event subscribers were found. Notifications are currently created by direct service calls; the proposed durable outbox and messaging channel adapters do not exist. Emitting an account-registration event therefore does not, by itself, create a notification. Pending registrations are separately counted on the staff dashboard.

**Domain map**

| Domain | Implemented responsibility |
|---|---|
| `core` | Shared model bases, rate-limit events, event bus, UI tags and slots, design tokens/helpers, health and error views, styleguide |
| `accounts` | Email login, account status, registration, profile and password change, staff approval actions |
| `organizations` | Client companies, memberships and roles, onboarding, organization switching, shared tenant queryset/base model |
| `permissions` | Permission catalogue, roles, grants/denies, authentication backend, web/DRF guards, assignment scoping |
| `staff` | Staff profiles and client assignments, back-office navigation, dashboard/search, role management, client export and organization API |
| `cms` | Pages and typed sections, site settings, navigation, shared collections, blog, RSS, sitemap and rich-text formatting |
| `catalog` | Service categories, services, packages, inclusions, add-ons, FAQs, public catalogue and session quote selection |
| `leads` | Contact submissions, lead pipeline, enquiry inbox, quote requests and scope items, history, client replies and decisions |
| `subscriptions` | Client services, agreed price snapshots, lifecycle/history, quote conversion, portal entitlements and expiry command |
| `campaigns` | Shared campaign engine, status/assignment/history, service-type registry and abstract extension model |
| `seo` | Campaign extension, audits/issues, keywords/rankings, tasks, backlinks, goals, CSV import and client workspace |
| `notifications` | Per-recipient database notifications, read state, permission-based staff fan-out |
| `media` | Local/Cloudinary storage support, transformation presets and template helpers; no media-library model/workflow |
| `paid_ads`, `social`, `email_marketing` | Scaffolded domains and placeholders; shared campaigns can still represent work in these areas |
| `analytics`, `approvals`, `messaging`, `integrations`, `audit` | Scaffolded domains; their proposed business models/workflows are absent |

Quotes are implemented inside `leads`, not a separate `quotes` app. There is no installed `tracking` app. Consent records, GTM/GA4/RudderStack integration, centralized analytics/reporting, generic approval workflows, standalone client messaging, and immutable audit logs remain future work. There is no payment gateway or implemented invoice/order system.

**Data and workflows**

```text
User ── OrganizationMember ── Organization
StaffProfile ── StaffClientAssignment ── Organization
StaffProfile ── Role ── RolePermission ── Django Permission
User ── UserPermissionOverride ── Django Permission

ServiceCategory → Service → ServicePackage
                         → inclusions / FAQs / add-ons

Session selection → ContactSubmission + QuoteItem snapshots
                  → Lead + LeadActivity
                  → QuoteRequest + QuoteRequestItem + QuoteActivity
Accepted QuoteRequest → ClientSubscription + SubscriptionEvent
Organization + optional ClientSubscription → Campaign + CampaignEvent
Campaign → optional SeoCampaignDetail
Organization → SEO audits / keywords / tasks / backlinks / goals
User → Notification
```

Public catalogue selection stores identifiers in the session and re-resolves availability and prices. There is one selection per service; selecting another package replaces its previous tier. Monthly and one-time totals are kept separate. Submitted selection labels/prices are preserved separately from the staff-editable quote scope.

Public submissions pass honeypot, timing, content and rate-limit checks. Accepted submissions attach to leads by normalized email and create activity. Spam is stored without creating the normal lead/quote/notification workflow. A quote submission adds a `QuoteRequest`; staff review scope and pricing, publish a proposal, and the client can reply or decide inside the portal.

Accepted quotes can be converted into pending client services. Conversion carries agreed amounts and reports skipped lines. Subscription activation is a separate operation. Active subscriptions unlock modules through `ServiceCategory.workspace_module`; expiry is performed by `expire_subscriptions`, not a background worker.

Campaigns use one table for all service types. They can reference a subscription, have an owner and assignees, and keep internal/client-visible history. SEO extends the campaign through a one-to-one detail model rather than creating another campaign engine. SEO measurements are entered manually or imported from CSV; they are not fetched from search providers.

SEO audits become client-visible on delivery. Client tasks require a client summary; client backlinks are limited to live links. Keyword readings are unique per keyword/date. Goal progress is calculated from existing SEO records.

The account, lead, quote, subscription and campaign lifecycles are declared as transition maps. These maps provide useful consistency but do not automatically serialize simultaneous writes.

**Authorization and organization context**

`User.status` determines `is_active`; there is no separate writable active flag. `user_type` distinguishes clients/staff/super admins. Django's `is_staff` separately controls Django-admin access.

For ordinary staff, platform access resolves deny overrides over grant overrides over role permissions, with default denial. Super admins are a special case. Clients use membership roles rather than platform permissions. The newer delivery policies combine the action permission with organization access through `permissions.access.can`.

`OrganizationOwnedQuerySet.visible_to` filters client records by active membership, but returns all records for staff. Staff selectors must therefore also apply `scope_to_accessible`. Subscriptions, campaigns and SEO generally follow this pattern. It is unsafe to assume the base queryset alone enforces staff assignments.

`CurrentOrganizationMiddleware` resolves a lazy `request.organization` from current memberships and the session. Settings and people pages use it. Several delivery queries instead accept only the user and aggregate all memberships; this inconsistency is confirmed below.

Internal history is filtered in client selectors. Shared tenant foreign keys use `PROTECT`, preserving business history when an organization still has work attached.

**The active file: `apps/staff/navigation.py`**

This file is the staff menu registry. `NavItem` stores the key, label, named route, permission, implementation flag, and placeholder description. `NavGroup` groups those items. `visible_navigation(user)` uses the central permission resolver and drops empty groups; `item_for` resolves metadata for placeholder pages.

The surrounding wiring is:

```text
staff/navigation.py
  → staff/context_processors.py
  → templates/admin/base.html + templates/admin/_nav.html
  → staff/urls.py
  → guarded domain views or staff/views/modules.py placeholders
```

Changing a menu entry does not implement or protect a feature. The route, view, selector/service policies, and tests must agree independently. Client navigation is a separate registry in `core/modules.py`, used by `subscriptions/guards.py`. `campaigns/registry.py` describes campaign types, while the older generic `core/registry.py` is not the current portal's source of truth.

SEO is marked built in staff navigation, but its client `PortalModule` still uses the default `built=False`. The client page can display real SEO content and still describe parts of the area as under construction.

**Frontend and content**

Shared layouts distinguish public, staff and client surfaces. The UI library provides inclusion tags, container components, and named slots. Tokens live in `assets/css/app.css`; variant mappings live in `core/design.py`. Django form styling is centralized in `core/forms.py`.

The JavaScript supplies overlay focus management, scroll locking, dropdowns, toast state, and file-drop interaction. Tests check component markup, context isolation, and accessibility attributes; this is not equivalent to browser-level keyboard or responsive verification.

The CMS uses controlled section types and registries for shared collections. Blog and body content use an escape-first, limited Markdown-like formatter rather than arbitrary stored HTML. Public selectors enforce publication status, including scheduled blog dates. Templates provide metadata, canonical links, structured data and navigation from database content.

The repository deliberately avoids invented client claims and sample dashboard metrics. Seed migrations contain substantial editable site/catalogue/blog content. Those seeds are historical initialization, not a general mechanism for updating a live site's editorial content.

**Verified findings**

Seven temporary probes were run against the isolated PostgreSQL test database. All reproduced the behavior described here. They assert the observed gaps, so their passing result is evidence of a problem, not a clean security result. The probes live outside the repository at `/tmp/test_heliograph_study.py`.

| Priority | Confirmed behavior | Relevant code |
|---|---|---|
| High | A staff account with no organization permission or client assignment can POST to the client member-removal endpoint and remove another organization's non-owner member. The view requires login, its queryset admits all staff, and organization policies broadly allow staff. | `organizations/views/workspace.py::remove_member`, `organizations/models.py::OrganizationMemberQuerySet.visible_to`, `organizations/policies.py::can_remove_member` |
| High | Staff holding only `quotes_view` can accept an unassigned client's proposal through the client decision route, bypassing the separate `quotes_approve` right. | `leads/views/client.py::quote_decision`, `leads/policies.py::can_client_see_quote`, `leads/quote_services.py::client_decision` |
| High | A client with the documented read-only `viewer` membership role can accept a proposal. Decision authorization uses visibility rather than a separate role-aware predicate. | `leads/quote_services.py::client_decision`, `leads/policies.py::can_client_see_quote` |
| High | A staff account with `quotes_view` and no assignments can retrieve another organization's quote. Quote selectors check the module permission without assignment scoping. Lead/inbox selectors show the same broad pattern in source. | `leads/selectors.py::get_quote_request`, `quote_requests`, `inbox` |
| Medium | Selecting organization A still displays an active subscription owned by organization B when the user belongs to both. Entitlements also aggregate memberships. SEO independently chooses the first membership organization. This crosses workspace context, although both memberships are authorized. | `organizations/views/workspace.py::overview`, `subscriptions/selectors.py::subscriptions_for_client`, `subscriptions/guards.py::entitlements`, `seo/selectors.py::client_workspace` |
| Medium | A suspended organization with an active subscription retains SEO entitlement. Membership and subscription status are checked, but organization status is not. | `organizations/models.py::OrganizationOwnedQuerySet.visible_to`, `subscriptions/guards.py::entitlements` |
| Medium | A staff member assigned only to organization A can create an A-owned SEO task linked to B's keyword through the service API. `full_clean()` does not supply a same-organization relation rule. The tested link is not exposed by the current task form, so this is a service/model boundary gap. | `seo/services.py::create_task`, `seo/models.py::SeoTask` |

These findings make authorization consistency the first maintenance priority. Hiding staff menu entries does not address them.

**Additional source-level concerns**

These were identified by inspection rather than concurrent or deployment experiments:

- Rate limiting performs a count followed by an insert. Simultaneous requests can both pass the count. The account documentation's claim that this avoids races is unsupported by the implementation.
- Quote references read the highest textual reference and increment it without locking or retry. Concurrent creations can collide; lexical ordering also becomes incorrect after the four-digit sequence width is exceeded.
- Lifecycle writes and the last-owner check lack row locking. Atomic transactions alone do not prevent competing decisions or two owners being removed concurrently.
- `OrganizationViewSet` uses DRF's default update path instead of `organizations.services.update_organization`. That bypasses the domain's normalization and event publication. The architecture import test misses standalone `api.py` files, so its passing result does not enforce the advertised rule on this file.
- `set_spam(..., is_spam=False)` recovers a lead but does not reconstruct a skipped quote request or normal notifications. A rescued quote submission can remain absent from the quote workflow.
- Several creation services accept privileged initial states without separately checking transition permissions. For example, campaign creation accepts `live` with create permission, although normal transitions require approve permission. Current staff creation forms do not expose that argument.
- `notify_permission_holders` checks the permission, not access to a specific organization. Once lead/quote assignment scoping is tightened, notification fan-out must be tightened with it.
- SEO import parsing does not handle every malformed CSV/numeric case: surplus columns can become list values, and conversion of infinite numeric text can raise `OverflowError`. This merits bounded malformed-input tests.

**Validation results**

| Check | Result |
|---|---|
| Full existing pytest suite | **1,714 passed, 5 failed, 2 skipped** in 46.60 seconds |
| Three SEO registration/extension tests run alone | **3 passed** |
| Temporary behavioral probes | **7 passed**, reproducing the findings above |
| Ruff | **3 violations**, all in SEO tests: two unused imports and an ambiguous `l` variable |
| Django check with test settings | No issues |
| Django production deploy check | No issues reported; one explicitly silenced mail check |
| Migration generation dry-run | No model changes detected; database history verification was unavailable in that sandboxed command |

The full test suite required access outside the filesystem/network sandbox to reach local PostgreSQL. Initial sandbox failures were database-connection errors, not application test failures. The successful full run used Django's test database.

The five existing test failures have specific causes:

1. The central tenant-isolation inventory still lists only campaigns/subscriptions and omits `SeoAudit`, `SeoGoal`, `Keyword`, `Backlink`, and `SeoTask`. Separate SEO isolation tests exist, but the inventory is stale.
2. Three SEO campaign tests fail only after `campaigns/tests/test_campaigns.py::test_registering_a_type_is_idempotent` overwrites the shared SEO registration with a minimal `CampaignType` and never restores it. All three pass in a fresh isolated run. This is test-state leakage, not evidence that normal application startup fails to register SEO.
3. The SEO empty-state test expects contiguous `until it is real` after replacing newlines with spaces; template indentation leaves multiple spaces in that phrase. The assertion does not normalize whitespace fully.

**Operations and documentation**

Configuration is split into base/dev/prod/test settings and environment values. Production enables secure cookies, HTTPS redirection and HSTS, serves compiled static assets with WhiteNoise, and selects local or Cloudinary media storage. `/healthz` checks database connectivity and returns 503 on failure.

Compose provides local PostgreSQL and a source-mounted Django server. The Docker entrypoint waits for PostgreSQL, migrates and creates the cache table. Railway configuration supplies build/start/health-check commands, and the Procfile declares migration/cache initialization. Actual platform deployment behavior was not verified.

`expire_subscriptions` and `purge_rate_limit_events` need an operational schedule; there is no built-in worker/scheduler. Production local media also needs a deliberate persistence/serving arrangement if Cloudinary is not used. No repository CI workflow or browser test harness was found.

The working tree was already almost entirely untracked at the start, so Git cannot provide a useful committed baseline for this study.

Documentation needs reconciliation: `ARCHITECTURE.md` says nothing is built, README says only the user model exists despite listing completed phases, the catalogue document describes the old handoff-only quote journey, and the content document still lists implemented modules as unbuilt. Current code and executable tests are the stronger source of truth.

The practical next sequence is to close the confirmed authorization gaps, make organization context/status consistent across the portal, restore a clean test/lint baseline, address relation validation and concurrency, and then continue the remaining product modules. The application's existing service/selector structure and shared component library provide clear places for that work.

## Phase 17 update — Social Media

Social Media is now implemented as an organization-scoped workspace over the shared
campaign engine. It adds channels, creator partnerships, scheduled content and
reels, deliverables, revision-specific client review decisions, and dated manual
performance observations. Staff assignments and selected-organization subscription
entitlements are enforced at the new entry points. Reviewers need an active owner,
admin or member membership; viewers remain read-only. There are no platform posting
or reporting integrations running. See [SOCIAL-MEDIA.md](SOCIAL-MEDIA.md) for the
workflow, model boundaries, permissions and reporting conventions.


## Phase 18 update — Email Marketing client service

Email Marketing now manages campaign email work, newsletters and automation-flow
plans beneath the shared campaign engine. It adds manual schedules, audience data,
external-execution status records, versioned deliverables and client reviews, and
daily recipient/open/click/conversion observations. Staff access combines action
permissions with client assignment. Client access combines the selected organization's
membership, active service entitlement, sharing flags and review role. This module
sends no system or marketing emails and has no outbound provider integration.
See [EMAIL-MARKETING.md](EMAIL-MARKETING.md) for its workflows and metric definitions.


## Phase 19 update — shared client approvals

The Approvals domain now contains ApprovalRequest, ApprovalComment and
ApprovalHistory. It supports client approve/change-request/reject decisions,
append-only discussion, staff cancellation, atomic history and in-app notifications.
Existing Social Media and Email Marketing review paths synchronize through the
shared service; a data migration preserves historical versions and decisions.
Staff and client dashboards show scoped pending counts and request lists. Access
requires current assignment or selected-organization membership, service entitlement
and source sharing. No email or SMS transport was added.
See [APPROVALS.md](APPROVALS.md) for the workflow and permission mapping.

## Manual client service workspace

The platform now defaults to manual operation, with Admin-controlled switches for
external integrations, the application API, tracking and public catalogue pricing.
Account-based quotation requests support catalogue services and custom briefs.
Private conversations, published progress reports and printable payment receipts
connect staff with individual clients, without requiring a service subscription.
The staff/client dashboards have a dedicated visual treatment, and administration
includes registration approval, public wording overrides and custom-role controls.
See [MANUAL-CLIENT-WORKFLOW.md](MANUAL-CLIENT-WORKFLOW.md) for permissions,
operating defaults, deployment steps and verification evidence.


## Platform refinement update

Admin and System Owner are now distinct account categories. Central feature
controls hide and guard disabled integrations, tracking and manual workspaces,
while keeping stored configuration. Individual catalogue price overrides and
private guest quotations extend the existing account quotation workflow.
Per-client workspaces now include invoices linked to receipts, messages linked
to quotes/services, editable progress reports with private attachments, and
accepted quotation-based renewal/extension/extra-service requests. Client
dashboards show published reports and invoice balances; public form labels and
choices are editable through Website wording.
See [PLATFORM-REFINEMENT.md](PLATFORM-REFINEMENT.md) for administration,
authorization boundaries, deployment and verification.

## Shared notification indicators

Admin, Owner and Client dashboards now include a mobile-visible notification bell,
personal notification inbox and live unread badges. New conversations and enquiry
rows are highlighted. Reading work acknowledges the current reader's related
alerts; other staff keep independent notification state. Authenticated read-only
polling updates counts without replacing forms. See [NOTIFICATIONS.md](NOTIFICATIONS.md).

### Unified payments and stable chat refresh

Invoices and payment receipts now share the per-client Payments workspace. New dashboard records receive automatic, concurrency-safe references; submission keys prevent duplicate issuance on repeated POSTs. Issued invoices provide a prefilled receipt action, support partial payments and show linked receipts and balances. Drafts can be edited before issue, and the printable documents share a design. Existing document references and client records are preserved. See `PAYMENTS-WORKFLOW.md` for behavior and deployment details.

Chat skips DOM swaps when a poll returns unchanged messages, retaining the reading position, search and composer. Timed browser checks verify the unchanged DOM and delivery of subsequent new messages.
