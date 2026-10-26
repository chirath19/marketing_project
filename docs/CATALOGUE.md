# Service catalogue

## Models

| | |
|---|---|
| `ServiceCategory` | Search, Paid, Social, Email, Analytics — name, slug, description, icon, order, visibility |
| `Service` | name, slug, category, short + full description, price, currency, billing type, image/icon, visibility, featured, order, **active**, **quote availability**, SEO fields |
| `ServiceFeature` | The "what is included" list, owned by the service |
| `ServicePackage` | Tiers of a service, with their own price and billing |
| `PackageFeature` | Which features a tier includes, and to what extent |
| `ServiceAddon` | Bolted on to a service, or sold alongside anything |

## Two switches, not one

`is_active` is whether the agency **still sells** it. `is_visible` is
whether it is **on the page**. Either one off takes a service down, and
the row is kept regardless — quotes and subscriptions reference it.

Retiring and hiding are also different *rights*: both need
`catalog_publish`, which is separate from `catalog_edit`, because showing
a price to the public is a different decision from writing the page.

## Prices

Stored as `DecimalField`, never a float: money that drifts by a hundredth
of a cent eventually disagrees with an invoice.

| Billing type | |
|---|---|
| `one_time` | Needs a price |
| `monthly` | Needs a price |
| `custom` | **Must not** have one |

The model enforces both directions. Some work genuinely cannot be priced
until it is scoped, and inventing a figure to fill the field would be
worse than saying so — the card reads "Custom quote", and the structured
data omits the offer entirely rather than publishing a price that does
not exist.

Whole amounts lose their decimals: `$2,400` reads as a price, `$2,400.00`
reads as an invoice line.

## Packages and comparison

A service with **two or more** visible tiers gets a comparison table;
one tier is not a comparison, so it is shown as a simple card.

Features belong to the **service**, and each package marks which it
includes. That is what lets the table show the same rows across every
tier without the list being retyped per tier — and a cell can carry a
value (`4 channels`) instead of a tick, which is what makes the table
worth reading.

A package can only include features from its own service; the model
refuses otherwise.

## The quote selection

Kept in the **session, not the database**. A visitor browsing has not
asked for an account and has not agreed to anything being stored about
them; a row per abandoned basket is data the agency neither needs nor
wants to be responsible for.

The session holds only identifiers. Names, prices and availability are
resolved from the live catalogue on every read, so:

- a price change shows immediately;
- a retired or hidden service **drops out on its own**;
- a deleted tier falls back to its service rather than losing the line.

Choosing a different tier of a service already selected **replaces** it —
nobody wants two tiers of the same thing on one quote. The selection is
capped, so a crafted request cannot grow a session unboundedly, and every
state-changing route is POST-only.

Totals keep **monthly and one-off apart**, because adding them produces a
number that means nothing. Anything custom-priced is excluded and flagged,
so the figure is never presented as complete when it is not.

## Sending a quote

The review page builds a pre-filled **email or WhatsApp message** the
visitor sends from their own account — the same rule as everywhere else in
this version: the platform sends nothing itself.

**This is where the phase stops.** A stored `QuoteRequest` that lands in
the staff Inbox belongs to the quotes module, which the dashboard already
lists. Until then the journey completes through the contact methods the
CMS manages, and nothing is pretended to be stored that is not.

## Admin

`/staff/services/` — the service list including retired and hidden ones,
with a per-service editor carrying its features, packages and the
comparison matrix. Categories ride the generic CMS collection registry;
add-ons have their own small screen.

Permissions: `catalog_view` · `catalog_create` · `catalog_edit` ·
`catalog_publish` · `catalog_delete`.

## Nothing is hard-coded

Every card, price, category, feature and add-on on the public catalogue
comes from the database. The twelve services seeded by migration come from
the supplied brief and are ordinary editable rows.
