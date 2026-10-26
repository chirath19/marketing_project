# Dashboard notifications and unread highlights

Admin, System Owner and Client dashboards share an always-visible notification
bell, including mobile screens. A gold count shows unread notifications. The bell
opens `/notifications/`, where unread updates have a **New** label and highlighted
background. Each account sees only its own notification records.

Messages, the staff enquiry inbox and quotation requests have navigation counts.
Staff client-workspace cards highlight conversations with new messages and sort
those contacts first. Incoming unread chat messages are highlighted when opened;
outgoing team replies do not appear as unread incoming work for colleagues.
Unread enquiry rows carry a visible **New** label, in addition to their background.

Counts refresh every ten seconds while the page is visible, and on window focus
or after chat updates. Refreshing counts does not mark anything read and does not
reload forms or discard drafts. The initial counts and all read actions work
without JavaScript. Accessible labels and a polite screen-reader announcement
accompany the visual indicators.

Opening a conversation acknowledges the reader's related message alerts. Other
staff members keep their own unread notifications. The existing shared message
read receipt continues to indicate that the agency team has opened the message.
Opening an enquiry or quotation clears its incoming-request count and the reader's
related alerts. Clients viewing their quotation acknowledge their own quote
updates, without marking the staff's incoming enquiry read.

**Mark all read** acknowledges the current user's visible notifications. It does
not change another user's alerts or claim that unread conversation content has
been opened. Disabled feature alerts stay hidden. Clients never receive the
agency's incoming-enquiry counts. Notifications link to permission-protected work;
opening another account's notification returns 404. Read actions on the shared
notification inbox use CSRF-protected POST requests, and external destinations
are not followed. Summary responses are authenticated and never cached.

These changes use existing notification/message/enquiry records: no schema
migration, outbound email, SMS, push provider or browser notification permission
is required. Rebuild static assets with `npm run css` and collect them using the
normal deployment process.

## Verification

- Full regression suite: **2,319 passed, 2 existing skips**.
- Final quotation-read and related authorization checks: **230 passed**.
- Chromium verified live updates for Admin and Owner after a new enquiry and
  client message; independent staff read states; client alerts for a team reply;
  notification navigation; and count clearing after reading.
- Seven desktop/mobile surfaces passed automated axe WCAG 2 A/AA and 2.1 AA scans
  with zero violations and no horizontal document overflow or JavaScript errors.
  This is an automated check, not an accessibility certification.
- Screenshots use disposable preview accounts and synthetic enquiries in a
  separate test database, never live client data.

[Accessibility results](notification-workflow/accessibility.json) ·
[Admin bell](notification-workflow/admin-bell.png) ·
[Owner on mobile](notification-workflow/owner-bell-mobile.png) ·
[Client inbox](notification-workflow/client-notifications-mobile.png) ·
[Unread conversation](notification-workflow/unread-conversation-mobile.png) ·
[New enquiry](notification-workflow/new-enquiry.png)
