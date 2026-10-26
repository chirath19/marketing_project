# Quote requests

## Three records, not one

A quote request is the third record in this domain, and deliberately not
a fourth use of the first two.

| | |
|---|---|
| `ContactSubmission` | What somebody sent, **never edited**. Evidence. |
| `Lead` | The relationship with a person or company. One per email, reopened when they come back, long-lived. |
| `QuoteRequest` | **One specific ask.** Its own status, owner and scope. |

The same client can have three quotes open at three different stages.
Folding them into the lead would make *"which quote did they accept?"* a
question nobody could answer.

`QuoteRequestItem` is the agency's working copy of the scope, seeded from
the `QuoteItem` rows on the submission. The submission's copy keeps the
price **as the visitor was shown it**; this one is free to become what is
actually being quoted. The difference between the two is often the useful
part, which is why dropping a line sets `is_included = False` rather than
deleting it.

## Nothing is sent

No email, no SMS, no outbound anything — the same rule as every other
module. A new request:

1. is stored, with its lines and their prices as shown;
2. raises an in-app notification addressed to **everyone holding
   `quotes_view`**, so it can never reach somebody who could not open it;
3. appears in the staff pipeline at `/staff/quotes/`;
4. appears in the client's own workspace, if they were signed in.

Tests assert `mail.outbox` is empty after a submission and after a client
accepts.

## The workflow

```
new → reviewing → clarification_required ⇄ proposal_ready
                                              ↓
                                     accepted / declined → closed
```

Transitions are declared as data in `quote_services.ALLOWED_TRANSITIONS`,
so an unexpected move raises rather than quietly rewriting history.

Two rules are worth stating:

- **An accepted quote cannot be un-accepted.** The client agreed;
  pretending otherwise loses the only record that they did. It can be
  closed, not reopened.
- **A declined or closed quote can be picked back up.** People change
  their minds, and a quote that cannot be reopened gets re-keyed as a
  duplicate.

## Rights

| Right | Covers |
|---|---|
| `quotes_view` | Read the pipeline and any quote |
| `quotes_edit` | Scope, prices, notes, attaching a client |
| `quotes_assign` | **Give a quote an owner** — handing out work is its own decision |
| `quotes_approve` | Record that a client accepted or declined |

`quotes_approve` is separate on purpose: adjusting a price is day-to-day
work, recording a commercial commitment is not.

## What the client sees

This is the first record in the platform a client can open, so the
visibility rule has two halves and lives in one place
(`QuoteRequestQuerySet.readable_by`):

- quotes belonging to an organization they **actively** belong to, and
- quotes they personally submitted.

The second half matters because a visitor can send a quote before an
organization exists for them, and should not lose sight of it the moment
they register.

Deliberately **not** `OrganizationOwnedModel`: that base requires an
organization, and a quote request can arrive without one. The name
`visible_to` is reserved for the tenancy rule, so this one is called
`readable_by` — an architecture test enforces that.

### What is withheld

- **Internal notes.** Every `QuoteActivity` declares `is_internal`, which
  defaults to `True`: the safe mistake is a note the client does not see.
  Filtering happens in the selector, not the template, because a
  condition forgotten in one template is how a staff note leaks.
- **The scope summary**, until the status reaches `proposal_ready`. A
  half-written note read mid-draft causes exactly the conversation it was
  meant to prevent.
- **Totals**, until there is a proposal. Showing a running figure while
  it is still being worked out invites an argument about a number nobody
  has agreed.

### What the client can do

Reply on the quote (stored in-app; the owner is notified directly, or
everyone holding `quotes_view` if it has no owner), and accept or decline
once it is `proposal_ready`. Accepting earlier is refused — there is
nothing to accept until there is something to accept.

### What the client is told

In-app only. The submitter (or, for a quote with no submitter, the active
client members of its organization) is notified when the quote reaches
**Clarification needed**, **Proposal ready**, **Accepted** or
**Declined**, and whenever staff reply. Internal moves (`reviewing`),
scope edits and internal notes stay silent.

## One conversation per quote

`apps/leads/quote_thread.py`. When the quote belongs to a signed-in
client of an active organization, a reply on the quote — from either
side — is a `messaging.Message` tagged with the quote, in that client's
private conversation. The same words show on the quote page and in the
Conversation tab, and a message tagged with the quote from the
Conversation tab shows on the quote. Other members of the organization
do not see the submitter's private messages.

Quotes without such a client (guest requests) keep replies on the quote
timeline as non-internal `QuoteActivity` rows, which is where those
readers can see them.

Staff write in one composer with two modes: **Reply to client** (always
visible to the client) and **Internal note** (always staff only). There
is no checkbox to forget.

## Accepted means active

Accepting — by the client, by staff, or through a guest link — activates
the quote's included catalogue lines as **active** client services
(`subscriptions.services.activate_accepted_quote`). The quote then reads
**Active** everywhere and appears under **Active work** in the client's
quote list, with its services linked.

- No organization? The submitter's own organization is attached. A guest
  quote waits, with an internal note, until staff attach one — activation
  then happens on attach.
- Quotes behind a service change request are skipped; `changes.apply`
  turns those into services itself.
- Anything that could not be activated is written to the internal
  timeline; the staff page still offers a manual "Create the services".

## References

`QR-2026-0001`: year plus a per-year sequence, generated inside the
creating transaction against a unique column. Derived from the year
rather than the primary key so the number a client reads back over the
phone says roughly when they asked.

## Where it is wired in

- `record_submission` creates the quote, so every request takes one path.
- A signed-in client's quote is attached to them and their organization
  at creation, so nobody has to match it up by email later.
- Staff dashboard: **Open quotes** and **Unread quote requests**.
- Client workspace: their quotes, with a banner when one awaits them.
- The raw submissions stay reachable at `/staff/quotes/submissions/`.
