# Social Media workspace — Phase 17

Staff open **Delivery → Social media**, select an assigned client, and manage work
at `/staff/social/<client-slug>/`. Clients open **Social media** in their portal
(`/organization/area/social/`). There is no automatic posting, account connection,
platform credential storage, live reporting adapter, or sample dataset.

## Staff workflow

1. Create a shared **Social Media campaign** using the existing campaign engine.
   Campaign creation/status/assignment retain the campaign permissions. The social
   workspace links to those pages and shows campaign status and client summaries.
2. Add a channel with a platform, account name, handle and optional profile link.
   Instagram, Facebook, LinkedIn, TikTok, YouTube, X and Other are supported. A
   used channel's identity is fixed; deactivate it or create another account.
3. Optionally add a creator partnership under the campaign, with a brief, due date,
   proposed/active/completed/cancelled status and client visibility. Internal notes
   remain staff-only. Associate its deliverables through its content items.
4. Create a post, short video/reel, video, story or other content item. Enter its
   caption and optional scheduled date/time. The form names the current timezone.
   Campaign, channel and partnership associations are fixed once the item exists.
5. Add deliverables with a description, external review link and optional due date.
   Content, partnerships and deliverables default to internal. Share both the item
   and its deliverable before requesting client review. Each deliverable defaults
   to requiring client approval; staff may explicitly make a review optional.
6. Request review. Clients review the submitted text, link, format, channel and
   planned date. They can approve, request changes or reject with feedback.
7. After all required deliverables have current approvals, mark the item scheduled.
   This is a planning status only. After publishing manually, record its actual
   publication time and public URL; that action additionally needs `social_publish`.
8. Record results per content item and date. Re-entering an existing date replaces
   that observation and requires edit access. Enter daily increments, not lifetime
   counters, and identify the source. Zero means an observed zero; absent observations
   are displayed as absent, not fabricated performance.

Published content and deliverables are preserved. Create a new content item for a
new version. Staff can still correct internal notes and daily results. There are no
hard-delete controls that could remove the review or performance history.

## Client access and approvals

Every request checks active membership, the selected organization's operational
status, and that organization's active Social Media service. Having Social Media
in another organization does not grant access to the selected organization.

Clients see shared content, shared creator briefs, and only deliverables explicitly
shared under shared content. Internal notes are never rendered in client pages.
Owners, admins and members can respond to reviews; viewers can only read. Staff,
including super admins, cannot impersonate a client's approval decision.

`SocialApproval` belongs to a deliverable and records its revision, the parent
content revision, a submitted snapshot, requester, decision maker/time and feedback.
Edits to reviewable content cancel pending reviews and increment the revision.
Approved decisions remain in history but cannot authorize a changed revision.
Internal-note edits do not invalidate approval. Deliverable changes return scheduled
work to draft; publishing and scheduling always recheck current required approvals.
Changes requested can be followed by another review round. Repeated decisions and
stale browser submissions are rejected. Writes lock the content parent before its
children to serialize review/edit/publication changes.

Snapshots preserve submitted text and links, not copies of externally hosted files.
Use a version-specific asset URL and set its sharing permissions deliberately.
Changing a file behind an unchanged URL cannot be detected by this module.

Phase 19 connects these reviews to the shared [Approvals workspace](APPROVALS.md).
Requests, decisions and revision cancellations now update shared history, in-app
notifications and dashboard indicators atomically. The existing Social Media review
URLs remain valid; shared review pages add comments and full transition history.

## Permissions and architecture

- Staff reads: `social_view` **and** client assignment (or all-client access).
- New channels, partnerships, content, deliverables and observations: `social_create`.
- Edits, review requests and status updates: `social_edit`.
- Recording publication: `social_edit` plus `social_publish`.
- Campaign management uses the existing `campaigns_*` permissions.
- Django admin does not expose unrestricted write forms for these records.

Persistence lives in six tenant-owned models: `SocialChannel`, `CreatorPartnership`,
`ContentItem`, `SocialDeliverable`, `SocialApproval` and `SocialMetric`. Campaigns reuse
`campaigns.Campaign` with `service_type="social"`. Content, deliverables and reviews
use UUIDs in public URLs. Related-record validation prevents cross-client/campaign
links. HTTP forms use scoped choices; services independently authorize writes.

The workspace filters by campaign, channel, format, status and dates. Date bounds
are inclusive: the schedule uses `scheduled_at`, while results use the observation
date. A date-filtered schedule omits unscheduled items. KPIs summarize matching
recorded observations. Daily results include impressions, views, likes, comments,
shares, saves, clicks and leads. Reach is deliberately not summed across posts/days.

`apps/social/integrations.py` defines a reporting-provider protocol and daily
observation value object. Channel and content external IDs are reserved for future
adapters. An adapter must normalize platform data to daily increments and use the
same authorized services. No adapter is registered or executed, and there is no
posting method, worker or scheduler.

## Validation

`apps/social/tests/` covers the client and staff HTTP workflows, scoped reads,
sharing flags, tenant and campaign validation, membership and entitlement revocation,
review roles, CSRF, revision invalidation, publication permissions, observation
validation and correction. The initial migration creates the schema and its daily
uniqueness, pending-review uniqueness and publication constraints.
