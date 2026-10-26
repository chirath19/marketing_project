# Campaigns

One engine, every service area.

## Why one table

> *Create reusable campaign interfaces so service-specific modules extend
> this core system instead of creating unrelated architectures.*

An SEO campaign and a paid campaign differ in **what you measure them
by**, not in what they *are*. Both have a client, a budget, a period, an
owner and a status. Four campaign models would have meant four status
machines, four permission models, four isolation rules — and a combined
view assembled from four queries that agree about nothing.

So there is one `Campaign` table. `service_type` discriminates, and it
uses the **same vocabulary as the portal** (`apps/core/modules.py`), so a
campaign of type `seo` lands in the client's Search area with nothing to
map between the two.

## The extension point

`apps/campaigns/registry.py`. A service module declares a type rather
than subclassing anything:

```python
register(CampaignType(
    key="seo",
    label="Search",
    goal_label="Target positions",
    detail_model="apps.seo.models.SeoCampaignDetail",
))
```

`goal_label` is why this is worth doing: "Target positions" and "Cost per
customer" are not the same question, and one generic *Objective* label
serves neither. The form reads it from the registry.

Where a type needs fields the core does not have, it attaches them:

```python
class SeoCampaignDetail(CampaignDetail):     # apps/campaigns/models.py
    target_keywords = models.TextField(blank=True)
```

`CampaignDetail` is an abstract base with a `OneToOneField` to the
campaign. `campaign.detail` resolves it through the registry, so the core
never imports a service module — the dependency points one way only.

Reading is the same shape:

```python
selectors.visible_campaigns(actor, service_type="seo")   # staff
selectors.campaigns_for_client(user, service_type="seo") # client
```

The client's combined Campaigns page and each service area's own page are
**that query with a different argument**, not two code paths. A test
asserts a service area shows only its own.

## Lifecycle

```
planned → live ⇄ paused → done → (live again)
   ↓        ↓       ↓
cancelled ──┴───────┘
```

Declared as data in `services.ALLOWED_TRANSITIONS`.

- **Cancelled is the dead end.** The work was called off; restarting it
  should be a deliberate new campaign, not a dropdown.
- **Done can run again.** A seasonal campaign that returns next year is
  the same campaign, and re-keying it loses its history.

Going live stamps `started_at` and, if blank, `starts_on` — so "when did
this actually start?" has an answer nobody has to reconstruct.

## Rights

| Right | Covers |
|---|---|
| `campaigns_view` | Read the list and any campaign |
| `campaigns_create` | Start one for a client |
| `campaigns_edit` | Detail, budget, dates, notes |
| `campaigns_assign` | **Owner and who is working on it** |
| `campaigns_approve` | **Take it live, pause, finish, cancel** |

`approve` is separate because taking a client's advertising live commits
their budget. `assign` is separate because handing out work is a
different decision from doing it — the same split as leads and quotes.

## Isolation

`Campaign` inherits `OrganizationOwnedModel`, the single implementation
of the tenancy rule. On top of that, staff are narrowed by **assignment**
(`scope_to_accessible`), and the service layer re-checks the permission
against the campaign's own organization — so the rule holds for a future
SEO module, an API or a command, not just the views.

`apps/campaigns/tests/test_isolation.py` drives it at the queryset, the
selector, the client's pages and the staff pages. It includes a search
test, because a search box is a classic way round a scoped list, and a
`service_type` test, because filtering must narrow a scope and never
widen it.

## Internal and client-visible

`description` and `internal_notes` are staff-only; `client_summary` is
written to be read by the client. Every `CampaignEvent` declares
`is_internal`, defaulting to `True` — the safe mistake is a note the
client does not see. Filtering happens in the selector, never the
template.

## Adding a service module later

1. `register(CampaignType(...))` in that app's `AppConfig.ready()`.
2. Add a `CampaignDetail` subclass if it needs extra fields.
3. Read through `selectors` with `service_type=` set.

Nothing in the core changes, which is the point.
