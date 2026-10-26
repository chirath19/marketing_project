# Public website redesign

## Scope and audit

The October 2026 redesign covers the public CMS pages (Home, About, Contact,
Privacy, and future CMS pages), catalogue and categories, individual services and
pricing packages, blog listings/categories/tags/articles, enquiry and quotation
journeys, sign-in/registration, confirmation pages, and branded errors.
Admin, Staff, and Client workspaces retain their existing shells, tokens, shared
components, JavaScript, and templates. No content records or migrations are
changed by this redesign.

The initial audit found:

- A nearly white canvas and the same oversized hero treatment on multiple pages.
- Dark cards with light-surface text colors in add-ons and single-package pricing.
- Repeated feature grids, including a process that needed a sequential layout.
- Plain article reading surfaces and no visible blog search.
- Reveals that hid content before JavaScript completed; a failed script could
  leave whole sections invisible.
- A full-screen mobile menu with incomplete keyboard/focus behavior.
- A CSS cascade error: card, navigation and effect rules had accidentally landed
  in the stronger prose layer, overriding utility and composition styles.
- Quote and contact forms whose sections and next steps were visually unclear.

## Research and direction

References reviewed:

- [Land-book](https://land-book.com/): compare light surfaces, big type, visible
  borders, editorial treatments and agency compositions.
- [Awwwards agency collection](https://www.awwwards.com/websites/agency/): compare
  expressive hero work with service/navigation clarity.
- [CSS Design Awards service gallery](https://www.cssdesignawards.com/website-gallery?industry=services&page=1):
  compare visual hierarchy, interaction, and service presentation.
- [Instrument](https://www.instrument.com/): agency positioning and editorial
  organization of capabilities and work.

These informed the design judgment; no layout, copy, or artwork was copied.
A full dark theme would conflict with the brief. A pale SaaS layout would repeat
the original weaknesses. The selected direction pairs warm pearl surfaces with
navy cards, amber details, bold sans-serif headings, and selective serif accents.

| Decision | Implementation |
| --- | --- |
| Canvas | Pearl `#f3f1ea`, paper `#f8f6f0`; cool sage and warm amber atmosphere |
| Main ink | Existing navy and midnight brand colors |
| Cards | One navy gradient material; featured items differ by border and label |
| Typography | Self-hosted Inter Variable; Instrument Serif on closing statements |
| Artwork | Original inline SVG folded-light sculpture; CSS page-specific fields |
| Glass | Header and form panels, with an opaque fallback |
| Rhythm | Fluid section spacing, bounded reading widths, responsive columns |
| Interaction | Small hover lift, native disclosures, optional one-time entrances |

Home uses a two-column opening and sculptural artwork, followed by actual
catalogue disciplines, dark capability cards, editorial story sections, a
sequential process, FAQ, and a contained closing call to action. About uses an
arched artwork composition and editorial company-story sections. Services use a
compact introduction, category filters and consistent cards with separate detail
and add-to-quote actions. Contact uses a two-column enquiry composition. The quote
page explains the journey, keeps the selection editable, and separates contact
and project fields. Blog articles have a warm reading surface and a featured
editorial card. Legal pages use smaller headings and a clear text hierarchy.

## Source map

- `assets/css/app.css`: product system plus the public source import. The shared
  declarations are unchanged.
- `assets/css/public.css`: public tokens, typography, layouts and components;
  bundled through the existing `npm run css` command.
- `static/js/site.js`: public-only progressive enhancements, approximately 4 KB
  uncompressed; no new runtime libraries.
- `templates/public/base_site.html`: public navigation, footer and asset loading.
- `templates/public/_backgrounds.html`, `_sculpture.html`, `_motif.html`: decorative
  art, hidden from assistive technology and unable to intercept interactions.
- `templates/cms/sections/`: CMS section presentation; all copy, media, ordering,
  visibility, collection membership and CTA values remain editor-managed.
- `templates/public/catalog/`, `blog/`, `leads/`: public feature templates.
- `apps/core/templatetags/site.py`: published service disciplines for the home strip.
- `apps/cms/views/blog.py`: bounded public article search; matches title, excerpt,
  and content within the existing published/category/tag querysets.

The `site-prose` layer outranks utility styles only for formatted CMS text.
Other public components stay in the normal component layer. Public form styling
is scoped under `.site-form`; shared form controls and their accessible error
wiring are preserved.

## Behavior and content guarantees

- Navigation, disclosures and forms work without JavaScript. The mobile menu is a
  native, non-modal disclosure; Escape closes it and returns focus to its summary.
- Content is visible even if public JavaScript fails. Entrances translate content
  once instead of hiding it. Reduced-motion preferences disable decorative motion.
- Returning through browser history clears form busy state so a form can be used
  again. Actual duplicate submission and spam rules remain in the backend.
- CSRF, signed form timestamps, honeypots, bound values, field errors, registration
  rules, session-based quotation actions and consent-gated tracking are retained.
- Cookie settings reopen the existing consent choices. No new tracking providers
  or external browser dependencies were introduced.
- Services, prices, staff profiles, testimonials, figures and articles come from
  existing data. Empty collections remain empty; no fabricated clients, results,
  portraits or metrics were added.
- Article search is capped at 200 characters, escaped in the form, preserves its
  query during pagination, and never exposes drafts or future publications.
- No outbound email, SMS, automatic social posting, or provider integration was added.

## Verification

- Full isolated-database regression run: **2,167 passed, 2 skipped**. The skips
  are the existing intentional design-system exceptions. Four new tests cover
  search publication boundaries, category scope, pagination and escaping.
- After the final error/statistics accessibility fixes, **220 affected tests passed**.
- `npm run css`, `node --check static/js/site.js`, Ruff, and Django system checks pass.
- 16 representative public routes rendered at 1440, 768 and 390 pixels; the other
  published service and article detail pages also rendered at 390 pixels. All
  completed successfully without document-level horizontal overflow.
- Axe 4.10.3 reported **zero WCAG 2 A/AA and 2.1 AA violations** on 14 public page
  types. [Machine-readable results](public-redesign/accessibility.json).
- Seven key routes also passed 320px overflow checks. Branded 400/403/404/500/CSRF
  errors and explicitly labeled statistics/testimonial/team fixtures passed visual
  and axe checks at 1440 and 390 pixels after fixing error-page contrast and
  definition-list semantics. Fixtures were rendered in memory, never published
  or saved to the database. [State-review results](public-redesign/states-review.json).
- Browser checks passed for native menu keyboard navigation and Escape focus
  return, FAQ disclosure, cookie preference reopening, quote add/remove, bound
  form errors, article search, and no-JavaScript content/navigation.
- Dashboard/base/UI file hashes and the shared CSS declarations match their
  pre-redesign versions.

Saved review images: [desktop home](public-redesign/home-desktop.png),
[mobile home](public-redesign/home-mobile.png), [blog](public-redesign/blog.png),
[contact](public-redesign/contact.png), [selected quote](public-redesign/quote.png).
These screenshots show existing local development content; they do not certify
business claims or advertising data.
The browser review uses local development content and screenshots at 1440, 768,
and 390 pixels, with additional narrow-phone and no-JavaScript checks. These are
local checks, not a claim about production Core Web Vitals or every browser engine.

## Subsequent client workflow update

The later [manual client workflow](MANUAL-CLIENT-WORKFLOW.md) adds separate
staff/client dashboard styling. Public service prices are now owner-controlled
and hidden by default. Catalogue selections lead to an account-based quotation
request, and public template wording can be edited through the CMS. The historical
dashboard-preservation check above describes the public redesign phase only.
