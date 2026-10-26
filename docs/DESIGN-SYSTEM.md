# Design system

Live reference: **`/styleguide/`** — every component in every state. It is
open in `DEBUG` and staff-only otherwise, and it is the surface each phase
checks for responsive and keyboard behaviour before being reported done.

## Where things live

| | |
|---|---|
| `assets/css/app.css` | Tokens and the shared base classes. Built to `static/dist/app.css`. |
| `apps/core/design.py` | Variant-to-class mapping, status tones, pure helpers. Unit-tested without rendering. |
| `apps/core/templatetags/ui.py` | The `{% load ui %}` tag library. |
| `apps/core/forms.py` | `StyledFormMixin` — control classes and aria wiring on Django widgets. |
| `templates/components/` | Primitive components. |
| `templates/components/business/` | Domain components composed from the primitives. |
| `static/js/ui.js` | Focus trapping, scroll lock, toasts, drag-and-drop. |

## Three shapes of component

```django
{% load ui %}

{# Leaf — an inclusion tag with documented keyword arguments #}
{% ui_button label="Add to quote" variant="primary" %}

{# Container — its body arrives as `slot` #}
{% component "card" title="Recent activity" %}
  <p>…</p>
{% endcomponent %}

{# Multi-slot — named blocks arrive as `slots.<name>` #}
{% component "modal" id="quote" title="Add a service" %}
  {% slot "description" %}We reply within one working day.{% endslot %}
  <p>body</p>
  {% slot "footer" %}{% ui_button label="Add" %}{% endslot %}
{% endcomponent %}
```

## Rules

- **No raw hex in templates.** Colour comes from tokens; a test fails the
  build on a hex value in any template. The one exception is
  `SITE_THEME_COLOR`, because a `<meta>` tag cannot read a CSS variable —
  and a test asserts it equals the navy token.
- **No bespoke control markup.** `{% ui_field %}` for bound Django fields,
  the `ui_input` / `ui_select` / … tags otherwise. Both use the same
  `ui-input` class, defined once.
- **Component arguments never share a name with a global context
  variable.** Context processors run for a component's own render, so an
  omitted `brand=` argument would render the global `brand` dict onto the
  page. Hence `heading=`, not `brand=`.
- **Direction is always passed, never inferred.** A falling cost per lead
  is good news; falling revenue is not. `{% ui_metric_card direction="good" %}`.
- **State-changing controls are forms.** Approve, reject and confirm post;
  they are never links, which a prefetch or a crawler can follow.
- **Responsive tables are CSS, not a second markup path.** Add
  `data-label="<column>"` to each `<td>`; below `sm` the row becomes a card
  and the labels become its headings.

## Accessibility contract

Asserted by `apps/core/tests/test_component_accessibility.py`:

icon buttons carry a visually-hidden name · search inputs have a real
label, not a placeholder · the active tab, nav item and breadcrumb carry
`aria-current` · unread state is announced in words as well as colour ·
dialogs are `role="dialog"`/`alertdialog` with `aria-modal` and a label,
trap focus, close on Escape and return focus to their opener · dropdowns
report `aria-expanded` · invalid fields get `aria-invalid` and
`aria-describedby` · radio groups sit in a fieldset with a legend · the
error summary links to the field that failed · skeletons are
`aria-hidden` behind a single polite "Loading" · progress bars report
their value.

## Opening overlays

Declarative, because Django tag arguments cannot express `x-on:click`:

```django
{% ui_button label="Open" data_ui_open="quote-modal" %}
{% ui_button label="Cancel" data_ui_close="quote-modal" %}
{% ui_button label="Saved" data_ui_toast="Campaign saved" data_ui_toast_tone="success" %}
```

An HTMX response can raise a toast with
`HX-Trigger: {"ui-toast": {"message": "Saved", "tone": "success"}}`.

## Inventory

**Primitives (37 templates):** button · icon button · badge · status badge ·
metric card · metrics grid · progress bar · card · section · page header ·
table · tabs · pagination · breadcrumbs · nav item · navbar · sidebar ·
sidebar group · search box · filter bar · alert · toasts · modal · drawer ·
dropdown · confirm dialog · empty state · skeleton · spinner · image ·
field · form errors · input · textarea · select · checkbox · radio group ·
file upload.

**Business (9 templates + metrics grid):** ServiceCard · ClientCard ·
CampaignCard · LeadCard · ApprovalCard · ReportCard · ActivityTimeline ·
NotificationItem · InboxMessageItem · MetricsGrid.

They read attributes off whatever object they are given — a model
instance, a dataclass or a dict — so they work before the domain models
exist. Each tag's docstring lists the attributes it reads.

## The public site is a separate system

The marketing redesign is documented in [PUBLIC-REDESIGN.md](PUBLIC-REDESIGN.md).
It uses `assets/css/public.css`, imported by the existing Tailwind entrypoint,
plus public-only `static/js/site.js` and `templates/public/base_site.html`.
The shared tokens and workspace shells above remain unchanged.

Public pages use warm light surfaces, consistent navy cards, self-hosted Inter
and Instrument Serif, CSS background artwork and inline SVG. Public forms retain
shared field components with narrowly scoped `.site-form` styling. Only formatted
CMS text uses the stronger `site-prose` cascade layer.

CMS page content, media, prices and collections remain dynamic. Reveals never
hide content, the mobile menu uses a native disclosure, and reduced-motion and
no-JavaScript fallbacks remain usable. Run `npm run css` after editing either CSS
source. The existing static-version tag fingerprints both the compiled CSS and
public JavaScript in development.
