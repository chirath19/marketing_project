# Shared conversation interface

Requests & Quotes and Messages now render the same conversation component for Clients, Owners and Admins. The quote view contains messages about that quotation and its timeline; Messages contains the client's wider conversation. Quotation-linked replies remain the same stored message in both views.

## Experience

- Consistent navy header, participant identity, readable message bubbles, date separators, unread highlights and sent/read receipts.
- Matching composer, keyboard behavior and 5,000-character reply limit across both locations.
- Quotation replies send without a full-page reload. Both latest-message views refresh every 10 seconds while the browser tab is visible; the composer is outside the polled region.
- Search filters the currently loaded entries. Older Messages history remains available through pagination. Search results explicitly describe this scope.
- Copy-message, jump-to-latest and expand/reduce conversation controls.
- Quotation and project links sit behind an optional composer disclosure.
- Staff notes have a separate composer mode, an explicit visibility explanation and an amber treatment. They remain excluded from client responses and the shared Messages conversation.
- The staff inbox is a searchable list with client identity, company and unread counts.

Refreshes retain search and reading position; new messages below the current reading position are announced. Failed network sends retain the draft. Quote validation errors render beside the retained draft, including its staff-note mode. Sending from older Messages history returns to the latest messages.

The refresh indicator describes update frequency; it does not claim that another participant is online or typing. Read receipts appear only on message records that support them.

## Implementation

Shared templates live in `templates/messaging/_thread.html`, `_entry.html`, `_composer.html` and `_icon.html`. The former quote and Messages templates are thin wrappers. Styling lives in `assets/css/chat.css`; interactions live in `static/js/workspace.js`.

Existing authorization, tenant isolation, messages, quote history and notification services are retained. No database migration is needed. Build the stylesheet with `npm run css` when deploying.

## Validation

Browser checks cover Owner, Admin and Client quote/Message screens at 1440px and 390px, plus the staff inbox. Sixteen page/viewport combinations passed automated accessibility checks and horizontal-overflow checks. The browser journey also verifies quote sending, shared history, private staff notes, live refresh while drafting, search, copy, expansion and preserving a draft after an aborted network request.

Screenshots and accessibility results are in `docs/chat-redesign/`. These contain fixtures from an isolated test database, not real client conversations.

## Idle refresh refinement

Unchanged polls now leave the feed DOM untouched, including while searching. Changed feeds restore scroll position immediately on `htmx:afterSwap`, and timed feed swaps use a zero settling delay. This removes idle blinking without disabling incoming messages or read-receipt updates. See `docs/PAYMENTS-WORKFLOW.md` for the combined payment/chat verification.
