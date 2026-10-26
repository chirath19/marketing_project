# Admin dashboard shell

The staff dashboard is the business tool. **Django's admin is not** — it
stays available to superusers for developer work and is linked from the
account menu only when `is_superuser` is set.

## Where things live

| | |
|---|---|
| `apps/staff/navigation.py` | The 23 sections, each with the permission it needs |
| `apps/staff/context_processors.py` | Resolves the menu once per request |
| `apps/staff/views/` | A package: `dashboard`, `clients`, `staff_admin`, `roles`, `modules` |
| `templates/admin/base.html` | The shell — sidebar, top bar, mobile drawer |
| `templates/admin/_nav.html` | One nav list, rendered into both |

Everything else is the Phase 2 component library: tables, pagination,
breadcrumbs, cards, empty states, search box, filter bar, drawer.

## Navigation

Declared once and filtered by `access.has_permission`. **That filtering is
presentation, not protection.** Every route behind a menu item carries its
own `@require_permission`, and three architecture tests hold the line:

- every view in a guarded module declares a permission;
- every nav item resolves to a real route;
- every nav item's permission exists in the catalogue.

Groups with nothing visible are dropped, so a specialist does not get an
empty "Administration" heading.

## Responsive

| | |
|---|---|
| ≥ 1024px | Fixed 16rem sidebar, search in the top bar |
| < 1024px | Sidebar becomes the shared drawer component, opened from the hamburger |
| < 640px | Search collapses to an icon linking to the search page |

The drawer is the same component the rest of the product uses, so focus
trapping, Escape-to-close and focus return come with it.

## No invented data

Sections whose module does not exist yet are **still real routes with real
guards**. They render an honest page: "not built yet", what the section
will hold, and which phase builds it. The nav marks them `soon`.

A test asserts that every unbuilt section says so and renders no table.
The reason is practical: a dashboard showing plausible-looking sample rows
during development is one nobody trusts once the real numbers arrive.

The dashboard home shows counts from real tables only — clients, staff,
organizations awaiting onboarding, registrations awaiting approval — each
behind the permission that governs it. A staff member with no permissions
sees an empty state, not zeroes.

## Adding a real module

1. Build the domain app.
2. Replace the entry in `apps/staff/views/modules.py` with the real view.
3. Set `built=True` on its `NavItem`.

The nav entry, the permission, the URL name and the authorisation tests do
not change.

## Search

One route, `/staff/search/`, over clients and staff. Results come from the
same selectors the list pages use and are run through
`scope_to_accessible`, so search can never surface a record a page would
have hidden. Tested: an unassigned client never appears.
