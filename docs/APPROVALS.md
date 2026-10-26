# Shared client approvals — Phase 19

The Approvals workspace collects campaign decisions and the existing Social Media
and Email Marketing deliverable reviews. It provides comments, permanent history
and in-app notifications. It sends no email or SMS and never publishes content or
executes a campaign after a decision.

## Workflow

Staff open **Clients → Approvals** (`/staff/approvals/`). The inbox defaults to pending
requests and supports status and title filters. Authorized staff can choose an
assigned client and request a campaign decision with a title and description.
Everything in the request and its discussion is client-facing.

For a versioned Social Media or Email Marketing deliverable, staff request review
from its existing workspace. The same review appears in this shared inbox. The
existing client review URLs remain valid and link to the shared discussion/history.

Clients open **Working together → Approvals** in their selected organization's
portal. They can:

- **Approve** the submitted request.
- **Request changes**, with an explanation.
- **Reject**, with an explanation.
- **Comment**, without changing the decision.

Owner, admin and member memberships may respond and comment. Viewers can read only.
Staff may discuss or cancel requests with the relevant permission; they cannot
make a client decision on the client's behalf.

A pending request can move to `approved`, `changes_requested`, `rejected`, or
`cancelled`. Those states are resolved and have a resolution timestamp. Decisions
cannot be overwritten or reopened. Submit another request or deliverable review
round after revisions. Discussion may continue after resolution without altering
the recorded outcome. Cancellation requires a reason. Comments are append-only;
there are no edit/delete controls that erase the conversation or history.

## Records

`ApprovalRequest` is organization-owned and has a UUID, campaign relationship,
title, description, requester, request time, status, client response, resolver and
resolution time. A versioned request also links one-to-one to its source review,
and therefore to its deliverable, and preserves its submitted snapshot.

`ApprovalComment` holds the request, author, body and creation timestamp.
`ApprovalHistory` holds the request, actor, timestamp, event kind, previous/new
status and explanatory text or comment relationship. Comment/history rows inherit
their tenancy through their protected request relationship.

Creation, decisions, cancellations and comments write history and notifications
within the same transaction. If one write fails, the whole action rolls back. State
changes lock the request; versioned reviews lock their content/work parent first,
then the source review and shared request. Duplicate or concurrent decisions have
one winner; subsequent submissions are refused.

## Integration with delivery work

Social Media and Email Marketing continue to own content, deliverables and revision
validation. All their supported review-request, decision and invalidation paths now
use the shared approval service. The shared request is the decision workflow;
legacy review status/response fields are synchronized transactionally to keep
existing publication/external-execution checks and URLs working.

A rejection, pending review or cancelled review cannot satisfy a required approval.
Editing submitted work cancels pending requests with a history entry and an in-app
notification. A completed approval remains attached to its original revision;
it cannot authorize changed work. Generic campaign requests preserve their title
and description and do not implicitly gate a campaign's lifecycle.

The migration imports existing Social Media and Email Marketing reviews, preserving
request/decision timestamps, snapshots, responses and statuses. Imported history
records describe the original request and known resolution. It does not invent
missing comments or replay notifications for historical records. The backfill is
idempotent.

External asset snapshots preserve the submitted URL and text, not copies of remote
files. Version-specific URLs and suitable external file permissions remain necessary.

## Access and notifications

Staff reads require `approvals_view` plus access to the client organization.
`approvals_create` permits new campaign requests and staff comments.
`approvals_approve` permits cancellation and staff comments; it does not let staff
impersonate a client's decision. Staff writes also require read access. Existing
deliverable request/revision actions retain their source module's permissions.

Clients require an active account and membership, an operational selected
organization, and an active service to open Approvals. Each request additionally
requires the entitlement for its campaign's service type. Linked content and
deliverables must remain explicitly shared. A service in another organization does
not unlock the selected organization's requests. Revoked membership, sharing or
entitlement closes access on the next request.

Notifications are database rows in the existing Notifications domain. Recipients
are currently authorized client members and staff who can read the request, excluding
the actor. The source requester may receive a link to their source workspace when
they have source access but no shared-inbox permission. Unassigned staff, inactive
accounts and revoked clients are excluded. Notification text is a generic pointer,
not a copy of private request text, so later revocation does not leave that text in
an old notification. No mail or SMS transport is called.

## Dashboard indicators

The staff dashboard displays a real pending count and the five oldest pending items
within its permission and client scope. The client overview shows **Waiting for client
approval**, its count and up to five requests for the selected organization. It no
longer reports that the client is caught up while those requests remain pending.
In-app unread indicators use the existing notification counts.

Indicators are queried from committed data on each page load; they do not use sample
values or a separately cached counter. There is no background push or polling worker.

## Verification

`apps/approvals/tests/` covers state transitions, immutable resolutions, comments,
notification recipients, rollback atomicity, client/staff roles, tenant and service
isolation, sharing revocation, POST/CSRF guards, dashboard counts, status filters,
source-review synchronization and backfill idempotence. A PostgreSQL concurrency
test checks that simultaneous decisions produce exactly one decision history entry.
No-send tests execute commit callbacks with email sending blocked and verify an
empty outbox. Existing Social Media and Email Marketing suites exercise their older
entry points against the shared workflow.
