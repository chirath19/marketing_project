# Email Marketing client service — Phase 18

This module manages **agency work performed for clients**. It does not send system
emails, marketing emails, previews or test messages. It does not run automation
flows, schedule jobs, connect to an outbound provider, or store sender credentials
or recipient lists. Its status changes and approval decisions update records only.

Staff open **Delivery → Email marketing** and select an assigned client at
`/staff/email-marketing/<client-slug>/`. Entitled clients use **Email marketing** in
their portal at `/organization/area/email_marketing/`.

## Records and workflow

The existing `campaigns.Campaign` remains the shared service campaign, with
`service_type="email_marketing"`. `EmailWorkItem` represents three types beneath it:

- **Email campaign**: a specific piece of campaign email work.
- **Newsletter**: an issue or newsletter project.
- **Automation flow**: the trigger, steps and exit conditions documented for a flow
  that the agency builds and operates in an external tool.

These types share scheduling, tenant permissions, review revisions and reporting;
there are no parallel campaign engines. Each record has a name, subject, brief,
planned audience description and size, scheduled date/time, status, result summary,
staff-only notes and explicit client visibility. A blank audience size is unknown,
not zero. No recipient addresses are required.

1. Create an Email Marketing service campaign using the shared campaign controls.
2. Add email work, choose its type, and record the copy, audience and plan. Schedule
   times use the timezone named by the form. Scheduling is a planning record only.
3. Add `EmailDeliverable` records containing copy, a preview/document link, a due
   date, sharing permission and whether client approval is required (default: yes).
4. Share the work and the deliverable, then request review. No notification email
   is sent. The client opens the workspace to approve or request changes.
5. After required current revisions are approved, staff may record a schedule or
   external execution. Record **Completed externally** for campaign/newsletter work,
   or **Active externally** for a flow, with an actual external execution time and
   reference. The active flow can later be recorded completed or cancelled.
6. Record dated `EmailMetric` observations from external reports, and write a
   client-facing result summary. No data is fetched from a provider.

Draft, in-progress and scheduled work can be revised or cancelled. Cancelling work
closes pending reviews. Executed and cancelled creative work is preserved; create
another work item for a new version. Result summaries and internal notes remain
editable after execution, and daily observations can be corrected. There are no
hard-delete controls that erase approved or reported history.

## Reviews and client access

A client request must satisfy all of the following: active account, active membership,
operational selected organization, and that organization's active Email Marketing
service entitlement. A subscription in another organization does not grant access.
Clients only see shared work and deliverables explicitly shared beneath it. Internal
notes are excluded from client templates and review snapshots.

Owners, admins and members can review; viewers can only read. Staff cannot submit
a decision on a client's behalf. `EmailApproval` captures the submitted work and
deliverable revisions, snapshot, requester, decision maker, timestamp and feedback.
A changes request requires feedback. Duplicate pending requests and repeated or stale
decisions are rejected.

Changing reviewable work or a deliverable cancels its pending reviews. Previous
approvals stay in history but cannot authorize the changed revision. Scheduled work
returns to draft after such changes. Client-facing result summaries and staff notes
are outside the creative revision and do not invalidate an approval.

Submitted snapshots preserve the text and external preview URL, not the contents of
a remote file. Use a version-specific URL and appropriate external sharing settings;
changes made behind an unchanged remote URL cannot be detected here. HTML supplied
as copy is rendered as escaped text, not executed as an email preview.

Phase 19 connects these reviews to the shared [Approvals workspace](APPROVALS.md).
Requests, decisions and revision cancellations update shared history, in-app
notifications and dashboard indicators atomically. Clients can also reject and
comment through the shared workspace. No sending or notification-email handler
is registered.

## Reporting conventions

`EmailMetric` is unique per work item and observation date. Values are **daily
increments** from an external report, never lifetime totals:

- `recipients`: recipient deliveries for that day, not a unique list size.
- `opens`: open events, including repeat opens.
- `clicks`: click events, including repeat clicks.
- `conversions`: attributed conversion events for the day.
- `source` and `result_summary`: where the observation came from and its explanation.

Enter all counts; use zero for an observed zero. Missing observations remain absent.
Counts must be nonnegative whole numbers. Dates cannot be in the future or precede
the recorded external execution. Re-entering a work/date corrects that record instead
of adding it again and requires edit permission.

Filters cover service campaign, work type, status and dates. Inclusive date bounds
filter scheduled dates in the work list and observation dates in the results table.
Leave dates blank to include unscheduled work. The KPIs sum matching observations;
planned audience sizes are not summed across repeated issues or flows. No unique-open
rate is inferred from event counts, and no sample values are presented as live data.

## Permissions and implementation

- `email_marketing_view` plus staff assignment (or all-client access) permits reads.
- `email_marketing_create` permits new work, deliverables and daily observations.
- `email_marketing_edit` permits revisions, review requests, status updates and corrections.
- Recording external execution also requires `email_marketing_publish`. This existing
  catalogue permission grants **recording** access only; it never dispatches email.
- The existing `campaigns_*` permissions govern shared service campaigns.

All four concrete models (`EmailWorkItem`, `EmailDeliverable`, `EmailApproval`,
`EmailMetric`) are organization-owned. Work, deliverables and reviews use UUIDs.
Related-record validation rejects cross-client links and non-email campaigns.
Selectors enforce read scope; transactional services independently enforce writes.
Child writes and reviews lock their parent work item, so edits, review decisions,
status updates and metric corrections serialize consistently. Django admin exposes
no unrestricted write forms for these models.

No outbound integration interface or provider implementation was added. Future
sending capabilities require a separate explicit phase and authorization design;
they must not be inferred from the current status labels or domain events.

## Verification

`apps/email_marketing/tests/` exercises all three work types, staff forms, client
reports, sharing and isolation, entitlement revocation, review roles, CSRF, stale
revision rejection, external-execution evidence, daily reporting and correction.
The workflow is also exercised with email sending blocked and commit callbacks
executed, asserting an empty outbox.
