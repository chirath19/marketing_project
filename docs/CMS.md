# CMS and public website

## Controlled sections, not a page builder

A page is an **ordered list of sections**, each of a predefined type.
There is no drag-and-drop canvas: one produces pages that look nothing
like the rest of the site, and no amount of review catches it afterwards.

Section types live in `apps/cms/sections.py`. Each declares which fields
it uses, which it requires, and whether it draws on a shared collection:

> hero · text block · feature grid · statistics · testimonials · team ·
> questions and answers · call to action · contact details · image and text

The editing form **shows only the fields the chosen type uses**, and
`PageSection.clean()` refuses one that is missing a required field — so a
half-configured section cannot reach the public site. An image without
alternative text is refused too.

Adding a type is an entry in `sections.py` plus a template in
`templates/cms/sections/<key>.html`. Nothing else changes.

## What is editable

| | |
|---|---|
| Pages | Home, About, Contact (routed by kind, so renaming a slug cannot break them) and any number of standard pages |
| Sections | Type, heading, subheading, body, image, two CTAs, background tone, columns |
| Repeating items | Features and statistics inside a section |
| Shared lists | Testimonials, team, questions and answers — written once, used on any page |
| Banners | Message, link, placement, and **dates, so a campaign strip takes itself down** |
| Navigation | Header and footer links, each pointing at a page *or* a URL, never both |
| Site details | Name, tagline, email, phone, **WhatsApp number**, address, social links, footer note, default SEO |
| SEO | Per-page title, description, share image, noindex |

**Ordering and visibility** are on every collection. Hiding something
keeps it in the admin and removes it from the site.

Nothing editable is hard-coded. The brand name in the header, the contact
details in the footer and the WhatsApp link all come from the database;
settings hold only the bootstrap defaults used before the row exists.

## The shared collection pattern

Six collections are driven by **one registry and one pair of views**
(`apps/cms/collections.py`). Adding blog posts or case studies later is an
entry plus a form — no new views, no new templates, and the permission
checks come along.

## Permissions

| Right | Covers |
|---|---|
| `cms_view` | Open the content screens |
| `cms_create` | Add a page, section or list entry |
| `cms_edit` | Change one, reorder it, hide it |
| `cms_delete` | Remove one |
| `cms_publish` | **Put a page live** — separate on purpose |

Preparing a page and deciding it is ready are different decisions, often
made by different people, so an editor without `cms_publish` can build a
page but not ship it.

## The public site

Open to the world by design, which is why it is the one module exempt
from the view-guard test. It renders **published pages only** — a draft is
a 404 for everyone, signed in or not.

**SEO:** per-page title and description with a fallback chain, canonical
URL, Open Graph and Twitter tags, JSON-LD `Organization` built from the
same editable settings the footer uses, `noindex` where asked,
`sitemap.xml` excluding drafts and noindex pages, and a `robots.txt` that
points at the sitemap and keeps crawlers out of the dashboard and API.

**Performance:** a page is a small fixed number of queries whatever its
length — sections and their items are prefetched and shared collections
resolved once per page, not once per section. A test caps it.

**Accessibility:** the FAQ is `<details>`, so it works with no JavaScript
and is keyboard-operable for free. Images cannot be saved without
alternative text. Everything is the Phase 2 component library, so the
focus treatment and contrast are the ones already tested.

## WhatsApp

`SiteSettings.whatsapp_number` builds a `wa.me` link — a floating button
and a contact card. It **opens the visitor's own app**; the platform sends
nothing, which is the same rule as everywhere else in this version.
