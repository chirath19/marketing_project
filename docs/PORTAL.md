# The client portal

One portal. What a client sees in it is a function of their active
services — not of code written for them.

## How a module is unlocked

`apps/core/modules.py` is the whole registry. Every module declares what
unlocks it:

| `access` | Meaning |
|---|---|
| `always` | Account-level. Every client has it, including one who has bought nothing. |
| `any_service` | Needs at least one **active** service. There is nothing to put on a campaigns page for somebody who is not a client yet. |
| `service` | Needs an active service in a category mapped to this module. |

The chain:

```
ServiceCategory.workspace_module   →  which module a service unlocks
ClientSubscription.status == active →  whether it is currently open
```

Pausing a retainer closes its area again; cancelling closes it for good;
a *pending* service opens nothing, because agreed is not the same as
running.

The visible navigation now follows the business workflow: Overview,
Requests & quotes, Projects & services, Messages, Payments and Account.
SEO, advertising, social and email work remain available inside relevant
projects rather than as separate main tabs. See
[WORKFLOW-REDESIGN.md](WORKFLOW-REDESIGN.md) for the current journeys.

## Hiding is not the control

> *The dashboard must not merely hide unauthorized modules. Backend
> permissions must prevent direct URL access.*

The workflow navigation and route guards both derive access from the same entitlements:

```
apps.subscriptions.guards.entitlements(user)
        ├── core.workflow.client_navigation(...) → primary workflow areas
        ├── project detail / shared work → permitted specialist links
        └── can_open_module(user, k)  → what the view enforces
```

A specialist link appearing inside a project means the view behind it will serve the
page; a link missing means the view will refuse it. They cannot drift
apart because they are one list. A stale bookmark, a tab left open after
a service was paused, or a hand-typed URL all meet the same rule — there
are tests for each.

**403, not 404**, for a module the client has not earned. The module is a
product feature whose existence is public: it is on the services page and
in the price list, so pretending it does not exist would be a lie that
helps nobody. What is private is *another client's data*, and that is
guarded separately by the tenancy rule — where a 404 **is** correct.

An unknown key is a 404. A module with a page of its own
(`/organization/services/`) is also a 404 at `/organization/area/…`: two
addresses for one screen is a trap for whoever maintains it.

## One view, not ten

`apps/organizations/views/portal.py` renders whichever module was asked
for, from its registry entry. Ten near-identical view functions would
drift apart within a month.

Unbuilt modules are honest about it: the page says what the area will
hold and which of the client's services opened it, and shows **no data at
all**. A plausible figure now is a figure nobody trusts when the real one
arrives. A test strips the markup and fails if a currency amount or a
percentage appears anywhere.

## The overview is two pages

Decided by one thing — whether anything is actually running.

- **Nothing active** → onboarding. What happens next, how to start, and
  their quotes. Not six empty panels and a row of zeroes.
- **Something active** → what needs them first (a quote awaiting a
  decision, a service not yet running), then three counts from real
  tables, then active services, recent activity and the areas they have
  earned.

Everything on it is read through a selector that applies the tenancy rule
and filters internal entries, so no template has to remember to.

## Adding a module later

1. Add it to `PORTAL_NAVIGATION` with its `access`, description and
   `will_show`.
2. Point a service category at it, if it is `service`-gated.
3. When the real page is built, set `built=True` and give it a
   `url_name`.

Tests already assert that every module declares how it is unlocked, that
every built module names a route that resolves, that every unbuilt one
says what it will hold, and that every module without its own page is
reachable when earned.
