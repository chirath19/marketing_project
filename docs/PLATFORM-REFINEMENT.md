# Platform refinement

This release extends the existing Django/PostgreSQL platform. It preserves the
public site's navy/gold design and all existing delivery modules, provider
adapters, tracking settings and historical data. Work is managed manually;
these changes do not send email/SMS, post to social networks or collect money.

## Admin, System Owner and Staff

Admin means the existing Super Administrator account category. Admin creates
System Owner accounts in **Staff → Add staff** and chooses **System Owner**.
System Owners have business-management permissions across clients, including
content editing, quotes, services, reports, payment records and staff management.
They cannot access operating settings, grant Django-admin access, create other
Owners/Admins or modify those privileged accounts. Ordinary Staff continue to
receive custom roles, granular permissions and client assignments.

Roles can delegate only permissions the acting manager holds. Admin-only feature
configuration cannot be delegated through a custom role. Individual permission
overrides remain Admin-only. Staff profiles support name/email edits and soft
removal: removal disables sign-in while preserving authorship and client history.

## Feature controls

**Admin → Settings** (`/staff/settings/`) groups the controls into operating mode,
catalogue/quotes, provider connections, website tags and client workspaces.

| Control | Default | Behavior |
| --- | --- | --- |
| External integrations | Off | Syncs are skipped before an adapter runs. |
| Application API | Off | API endpoints return 404. |
| Website analytics | Off | No tracking tags or analytics collection. |
| Individual providers/tags | On within their disabled parent | Both the parent and child must be enabled. |
| Manual delivery and client workspaces | On | Independently switch campaigns, SEO, Paid Ads, Social, Email Marketing, approvals, chat, reports, payments and service requests. |
| Public prices | Off | Individual catalogue visibility overrides still apply. |
| Account-first quote entry | Off | Guests can submit a request without registering. |

Disabled features disappear from Owner/Client navigation, feature widgets and
notifications, and protected routes/services refuse access. Reports and invoices
remain reachable if only chat is disabled. Combined campaign views filter disabled
service areas. Admin retains configuration access, but cannot execute a provider
sync while its switch is off. Switching off never deletes records or credentials.
The retained account-first option redirects the ordinary quote entry to sign-in;
the explicit guest entry (`/quote/?guest=1`) remains available.

## Pricing and quotations

Each service, package and add-on has **Price visibility**: inherit, show or hide.
Packages/add-ons inherit their service setting, then the global setting. Hidden
prices are omitted from public cards, detail pages, structured-data offers and
quote snapshots/totals. Staff still maintain prices and prepare agreed proposals.

Registered clients request catalogue work and/or a custom scope at
`/organization/quotes/new/`. Existing account/organization notices handle inactive
or staff accounts without a misleading missing-page error. Saved catalogue
selections survive sign-in.

Guests submit at `/quote/` and receive a private follow-up URL on the confirmation
screen. Only a SHA-256 token hash is stored; the link expires after 90 days. Anyone
holding it can read that quotation, discuss it and accept/decline a published
proposal. The page explicitly explains this, disables tracking, prevents caching,
suppresses referrers and excludes internal notes. No link is emailed. Connecting
the quote to a named account revokes guest access. Staff review/price/negotiate
through the existing Quotes workspace and convert accepted work to client services.

## Per-client workspace

**Client workspace** lets authorized staff select an individual contact within an
accessible organization. Clients need active membership and see only records
addressed to themselves in the selected organization. Another contact in the same
company cannot read their conversation, reports, invoices or receipts.

- Messages may reference a permitted quotation and/or purchased service. Existing
  in-app notifications, read indicators and automatic feed refresh remain.
- Reports may reference a purchased service and include summary, progress, status,
  milestones, completed work, next steps and private attachments. Staff can edit
  existing reports or publish drafts. Published reports appear on the client dashboard.
- Invoices contain a reference, scope, dates, currency and positive amount. Drafts
  stay private until published. Status/balance are calculated from linked receipts;
  no duplicate lifetime balance is stored.
- Receipts record payments staff have confirmed. A receipt can link an invoice and
  service; invoice/client/organization/currency must agree and the payment cannot
  exceed the remaining balance. Voiding a receipt restores the balance. An invoice
  with payments must have those receipts corrected before it can be voided.
- Both invoices and receipts have authenticated printable pages for browser PDF
  export. The platform does not charge a card or verify a bank transfer.

Reports retain `analytics_view/create/edit` permissions independently of website
analytics. Payments use `subscriptions_view/approve`; messages use
`messaging_view/create`. Each permission is combined with current client access.
Attachments are limited to ten per report, 5 MB each, with PDF/PNG/JPEG extension
and signature checks. Bytes are stored privately in PostgreSQL and downloaded
through an authenticated authorization check; there is no public media URL.

## Renewals, extensions and extra work

From a purchased service, clients can request renewal, a later end date, extra
work or another catalogue service. Each request creates an ordinary quotation.
Staff agree the price/scope; the client accepts; authorized staff then choose
**Apply accepted service change** under **Service requests**.

Applying is atomic and idempotent. Renewals update the agreed billing and service
period, extensions update the end date, extras append agreed scope, and additional
services use the accepted-quote conversion flow. Service history and in-app
notifications record the result. Accepting a proposal alone does not silently
change an existing service or take payment.

## Website editing

Admin and Owner use **Website content** for pages, sections, media, navigation,
banners, contact/brand details, FAQs, testimonials, team, blog and SEO metadata.
Catalogue screens manage service content, packages, add-ons and price visibility.
**Edit website wording** covers public headings, buttons, helper copy, quote
confirmation/guest text, public form labels and choice labels. These editorial
changes do not alter input names, validation or permissions.

## Deployment and verification

Run `python manage.py migrate` and `npm run css`, followed by the deployment's
normal static-file collection. Local migrations have been applied. Existing
records remain; the operating migration enables the requested guest quotation
entry for existing installations. Review the Admin controls after deployment.

Screenshots in [platform-refinement/](platform-refinement/) use isolated, disposable
preview records. They do not represent actual payments, client results or live
advertising data. The browser journey exercises sign-in, registered and guest
quotes, two-way chat, report publication/editing, private download, invoicing,
partial payment and an accepted extension. Automated accessibility results are
recorded in [accessibility.json](platform-refinement/accessibility.json).

### Verification results

- Full regression suite: **2,298 passed, 2 existing skips**.
- After final shared-form and notification changes: **897 targeted checks passed,
  2 existing skips**.
- Chromium client/Owner/Admin/guest journey: **passed** in an isolated test database.
- Ten reviewed desktop/mobile pages: **zero automated axe WCAG 2 A/AA and 2.1 AA
  violations**, no document-level horizontal overflow, and no browser JavaScript
  errors. This is an automated review, not an accessibility certification.
- Django system check, migration consistency check, Ruff, CSS build and JavaScript
  syntax checks passed. All migrations are applied locally.

Review images: [Owner dashboard](platform-refinement/owner-dashboard.png),
[client dashboard](platform-refinement/client-dashboard-mobile.png),
[client quotation](platform-refinement/client-quote-mobile.png),
[Admin controls](platform-refinement/admin-feature-controls.png),
[report](platform-refinement/report-mobile.png),
[invoice](platform-refinement/invoice-mobile.png), and
[guest quotation](platform-refinement/guest-quotation-mobile.png).
