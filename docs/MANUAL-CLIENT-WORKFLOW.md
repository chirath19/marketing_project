# Manual client service workflow

For the latest role separation, guest quotes, invoices, service-change requests and report attachments, see [PLATFORM-REFINEMENT.md](PLATFORM-REFINEMENT.md).

The platform starts in manual mode. Existing integration adapters, credentials,
tracking configuration, metrics, and API routes are retained.

## Operating settings

Only an Admin (Super Administrator) can use **Staff →
Settings** (`/staff/settings/`) to independently control:

| Option | Default | Effect |
| --- | --- | --- |
| External integrations | Off | Scheduled commands and manual provider syncs record a skipped run without creating an adapter or contacting a provider. |
| Application API | Off | `/api/` returns 404. Server-rendered pages and authenticated chat continue to work. |
| Website analytics | Off | No tracking script, tracking tags or consent banner is rendered; browser ingestion and server event collection are disabled. The analytics navigation/page is hidden from Owner and Client; Admin retains configuration access. |
| Public catalogue prices | Off | Prices, public totals and structured-data offers are withheld unless explicitly enabled for an individual service/package/add-on. Agreed client proposals remain visible to their recipients. |
| Account-first quotation entry | Off | Guest requests are available by default; signed-in requests and saved selections remain supported. |

Turning an option off does not erase historical data or saved credentials.
Manual service workspaces and progress reports remain available without external
integrations or website tracking. Media storage and ordinary website functionality
are independent of these marketing integration switches.

## Client journey

1. A client registers. Where registration approval is required, the owner opens
   **Dashboard → Approve registrations** to activate both the account and its
   pending owned organization. No activation email is sent.
2. The client chooses catalogue services and/or writes a custom request at
   `/organization/quotes/new/`. Hidden catalogue prices are not recorded as prices
   shown to the client.
3. Staff review the request in **Quotes**, add catalogue or custom proposal lines,
   set amounts, describe scope, and share replies using the existing quote history.
4. Staff publish the proposal; the permitted client accepts or declines it.
   Accepted or closed proposal scope is locked. Additional work needs a new quote.
5. The existing accepted-quote-to-service conversion and campaign workflow continue
   to handle delivery.

Client-submitted quotations are private to their submitter. Organization-level
quotes without a named submitter remain accessible to active members. A viewer
cannot accept a proposal. Staff quote reads and writes respect client assignments.

The new-request page explains account restrictions rather than showing a missing
page: staff accounts receive links to quotation management and the staff dashboard;
clients in pending, suspended or archived organizations see the activation step
required before submission. Their selected services remain saved. Clients without
a workspace continue to company setup. These notices do not grant submission
rights or change organization status.

## Client workspace

**Staff → Client workspace** lists eligible client contacts. The same contacts are
linked from each client detail page. Access to each tab is checked independently:

| Tab/action | Staff permission |
| --- | --- |
| Read conversations | `messaging_view` |
| Send a message | `messaging_create` |
| Read progress reports | `analytics_view` |
| Create a report or publish it when creating | `analytics_create` |
| Publish an existing draft | `analytics_edit` |
| Read payment receipts | `subscriptions_view` |
| Issue or void a receipt | `subscriptions_approve` |

All actions also require access to that organization. Client visibility requires
an active membership, an active organization, and the exact named recipient.
Two clients in the same company cannot read each other's private conversations,
reports or receipts. Changing the selected organization changes the client desk.
No active subscription is required to contact the team or view shared records.

### Conversations

Messages are stored before in-app notifications are raised. Notifications go only
to the recipient or staff allowed to read the conversation. The page refreshes the
message feed every ten seconds while visible, preserves a draft during incoming
updates, and provides pagination for older messages. Sending also works without
JavaScript. Read receipts distinguish sent messages from messages opened by the
other side. This is an in-app conversation, with no email/SMS delivery or external
chat provider.

### Progress reports

Reports contain a title, summary, reported progress, work status and next steps.
Drafts are staff-only. Explicit publication exposes the report to its named client
and creates an in-app notification. Progress is manually reported, not represented
as a live platform measurement.

### Payment receipts

Staff record a confirmed payment's reference, amount, currency, date, method and
description. Amounts must be positive and dates cannot be in the future. A receipt
has an authenticated printable page; the browser can save that page as a PDF.
The system does not charge cards, verify a bank transfer, or integrate a payment
provider. Issued receipts cannot be overwritten: voiding keeps the original
payment details, correction reason and timestamp visible, and notifies the client.
A replacement receipt uses a new reference.

## Content and staff administration

The existing CMS continues to manage page sections, navigation, brand/contact
settings, services/packages, FAQs, team members, testimonials and blog content.
**Website content → Edit website wording** adds searchable plain-text overrides
for the public headings, explanatory text and calls to action previously embedded
in templates. Each entry can be restored to its shipped default. Overrides are
escaped and cannot execute HTML or scripts.

Staff creation, client assignments and role assignment remain in **Staff**.
**Roles and permissions** now also creates, renames and deletes custom roles;
system roles remain protected from deletion. Roles combine the application's
implemented action permissions. The owner can manage per-person grant/deny
exceptions on a staff member's page. A deny takes precedence over every role.
Creating a role does not create a new application action or bypass its checks.

## Deployment and review

Run `python manage.py migrate` and `npm run css`. No environment secrets or
provider credentials need to be removed. Migrations add operating settings,
conversations/messages, manual reports, receipts and website-copy overrides.
The dashboard styling is scoped to staff and client layouts.

Browser screenshots in `manual-workflow/` use disposable test accounts and
clearly named preview records in an isolated database. They are review fixtures,
not actual client work, payments or advertising results.

### Verification

- Full regression suite: **2,245 passed, 2 skipped**. After the final sign-in and
  registration redirect corrections, all **116 account tests** passed again.
- After the dashboard contrast and receipt styling corrections, the targeted
  workflow, template and design checks passed: **492 passed, 2 skipped**.
- An isolated Chromium walkthrough passed account sign-in, custom quotation
  submission, two-way chat with automatic updates and draft preservation, report
  publication, receipt issuance/viewing, and disabled operating defaults.
- Seven desktop/mobile workspace pages, including the printable receipt, have
  **zero automated axe WCAG 2 A/AA and 2.1 AA violations** and no document-level
  horizontal overflow. This is a targeted automated check, not a certification.
  See [accessibility results](manual-workflow/accessibility.json).
- Ruff, Django system checks, migration generation checks, the CSS build and
  JavaScript syntax checks passed. All migrations were applied locally.

Review images: [staff dashboard](manual-workflow/staff-dashboard.png),
[client dashboard](manual-workflow/client-dashboard-mobile.png),
[conversation](manual-workflow/conversation-mobile.png),
[report](manual-workflow/report-mobile.png),
[receipt](manual-workflow/receipt-mobile.png), and
[operating settings](manual-workflow/operating-settings.png).
