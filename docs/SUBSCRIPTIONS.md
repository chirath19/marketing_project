# Client services

`ClientSubscription` is the relationship the rest of the platform hangs
off: one service, sold to one client, for a period. A campaign will
belong to one, a report will report on one, and **what a client sees in
their workspace is decided by which of these are active**.

## One workspace, not one per client

There is a single client workspace. Which parts of it a given client can
open is a function of their active services and nothing else:

```
ServiceCategory.workspace_module   →   the area a service unlocks
ClientSubscription.status == active →   whether it is currently open
```

The vocabulary lives in `apps/core/modules.py` — a small closed list,
because a module is a page somebody has to build, so inventing one by
typing a new string into the admin would unlock a screen that does not
exist. The mapping from category to module is a **field**, so a new
category can declare what it unlocks without a deploy.

Only `active` counts. A paused retainer closes its area again; a
cancelled one certainly does. Two services in the same category open
that area once.

## Isolation

`ClientSubscription` inherits `OrganizationOwnedModel`, which is the
single implementation of the tenancy rule. This domain does not get its
own opinion about who may see what — that is the entire reason the base
exists, and this is the first model to use it.

On top of tenancy, staff access is narrowed by **assignment**:
`visible_subscriptions` applies `scope_to_accessible`, so a specialist
assigned to three clients cannot list, open or change a fourth client's
retainer. The service layer re-checks the permission *against the
subscription's own organization*, so the rule holds for the quote path
and any future caller, not just the views.

`apps/subscriptions/tests/test_isolation.py` drives this at every layer
it could be broken at — the queryset, the selector, the client's pages
and the staff pages — rather than once at the top and trusted downward.

## Lifecycle

```
pending → active ⇄ paused → completed → (active again, on renewal)
   ↓         ↓        ↓
cancelled  expired  cancelled
```

Declared as data in `services.ALLOWED_TRANSITIONS`. Two rules worth
stating:

- **Cancelled is the one dead end.** It means the relationship ended
  badly or never started; reviving it should be a deliberate new
  agreement, not a dropdown.
- **Completed and expired can be picked back up.** Clients renew, and a
  renewal re-keyed as a new row loses the history of the first
  engagement.

`subscriptions_approve` is a separate right from `subscriptions_edit`:
pausing a client's advertising stops work and stops billing, which is not
the same decision as fixing a typo in a note.

## Expiry

A status, not a calculation at read time, so the history records when it
happened and the workspace stops showing an area the client is no longer
paying for. There is no scheduler in this version — a deliberate
constraint — so it runs from a command:

```
python manage.py expire_subscriptions --dry-run
python manage.py expire_subscriptions
```

Safe to run repeatedly. The staff list and dashboard surface anything
ending within 30 days, because an end date that passes unnoticed is
either work stopping without anyone telling the client or work continuing
without anyone billing for it.

## Two ways in, one path

**By hand** from a client's page, and **from an accepted quote**. Both
call `services.create_subscription`, so they cannot drift apart.

The quote path (`create_from_quote`) closes the loop Phase 11 left open.
It takes only the lines still in scope that point at a real catalogue
entry, carries **the price that was agreed** rather than the current list
price, and says out loud what it skipped — a line silently dropped is
how a client ends up unknowingly unbilled. Services arrive `pending`;
activating them is a separate, deliberate act, because that is what opens
their workspace.

## Prices are copied, not referenced

Price, currency and billing are read from the catalogue at the moment of
sale and stored on the row. A catalogue change next quarter must not
alter what an existing client is paying. The same reasoning as a quote
line, for the same reason.

## One open subscription per service

A partial unique constraint: a client can hold the same service many
times over the years, but not twice at once. That is a double-charge
waiting to happen and it makes "is this client getting SEO?" ambiguous.
The form catches it first so the person gets a sentence rather than an
integrity error.

## Internal and client-visible

Every `SubscriptionEvent` declares `is_internal`, defaulting to `True` —
the safe mistake is a note the client does not see. `internal_notes` on
the record is staff-only; `client_notes` is written to be read by them.
Filtering happens in the selector, never the template.
