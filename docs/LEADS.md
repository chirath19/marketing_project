# Leads, enquiries and the Inbox

## Nothing is sent

No email. No SMS. No automated outbound message of any kind. Every
submission is written to PostgreSQL and raised with staff **in-app** — a
notification row and the Inbox are the entire delivery mechanism.

A test asserts `mail.outbox` is empty after a submission, and the success
page deliberately never says "check your inbox for a confirmation",
because none is coming.

## Two records, kept apart

| | |
|---|---|
| `ContactSubmission` | What somebody actually sent, **never edited**. It is evidence. |
| `Lead` | The agency's working record: status, owner, value. Staff change this one. |
| `LeadActivity` | The timeline — enquiry received, note, status change, assignment. |
| `QuoteItem` | What was selected on a quote request, with **the prices as shown**. |
| `Notification` | One row per recipient, so "read" means read by that person. |

The staff detail page shows the submission as plain text with no form
around it, and a test asserts there is no editable `message` field on it.

## What happens on submission

1. The submission is stored, with a **hashed** address fingerprint — a
   record of an enquiry, not a log of who browsed.
2. It is matched to a lead **by email**, so a second enquiry joins the
   existing record instead of creating a duplicate somebody has to merge.
   A lead that was lost or archived is **reopened**: one still receiving
   mail is not closed.
3. Blank fields on the lead are filled in from the new enquiry.
4. A `LeadActivity` entry is written.
5. Everyone holding `leads_view` (or `quotes_view` for a quote request)
   gets an in-app notification. Resolved through the same permission
   system as everything else, so a notification can never reach someone
   who could not open what it points at. Suspended accounts are skipped.
6. The visitor is **redirected** to a success page, so a refresh cannot
   resubmit.

## Spam: flag, do not reject

Four layers, and only the first rejects:

| Layer | Behaviour |
|---|---|
| Honeypot | **Rejects.** A person cannot trip it by accident. |
| Signed render timestamp | Flags a submission made faster than anyone can type |
| Rate limit, 5/hour per address | Refuses with 429 |
| Content heuristics (links, phrases) | Flags |

Everything except the honeypot **stores the submission and flags it**,
because losing a real enquiry silently costs far more than a staff member
skimming past an advert. Flagged submissions create no lead and no
notification, so they cannot pollute the pipeline — and "Not spam"
**creates the lead they never got**, so a false positive is recovered
rather than merely unhidden.

A flagged visitor still sees the success page. Telling a false positive
they were rejected is how a real enquiry gets lost.

## Pipeline

`new → contacted → qualified → proposal → won / lost / archived`

Transitions are declared as data, so an unexpected move raises rather
than quietly rewriting history. A lost lead can be reopened; a won one
can only be archived.

| Right | Covers |
|---|---|
| `leads_view` | Read the Inbox and the pipeline |
| `leads_edit` | Notes, status, archive, spam, lead details |
| `leads_assign` | **Give a lead an owner** — handing out work is a different decision from doing it |
| `quotes_view` | The quote request inbox |

A client never sees any of it — their own enquiry is not a record they
are entitled to browse.

## Dashboard metrics

**Unread enquiries**, **new leads**, **unassigned leads** — two aggregate
queries, one per table, not three round trips for three numbers. Staff
without `leads_view` see zeroes. The sidebar badges unread enquiries and
unread notifications.

## Where the forms live

| | |
|---|---|
| `/contact/` | The CMS contact page, carrying a `contact_form` section |
| `/contact/enquiry/` | The form's own page, and its POST target |
| `/quote/` | The catalogue selection, now with a real submit form |

The quote form **keeps the selection if submission fails** — losing what
somebody spent five minutes choosing because they mistyped an email would
be unforgivable. And a quote item records the price that was **shown**,
so the request does not silently change when the catalogue does.
