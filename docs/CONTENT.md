# Content: what the site says, and who can change it

## Two rules

**Nothing is invented.** No client names, no case-study figures, no
awards, no years in business, no headcount, no testimonials. Where a
claim would need a fact nobody has supplied, the copy describes how the
agency works instead — which is true, useful, and does not go stale. A
test (`tests/test_content_quality.py`) fails the build if a public page
starts claiming a percentage increase or a return multiple.

**Nothing is promised that the platform cannot keep.** There is no
outbound email in this version, so no page tells anyone to check their
inbox, and the success pages say plainly that no confirmation is coming.
Reply times live in a settings field that **ships empty** — a turnaround
printed on the page is a turnaround somebody has to hit at five o'clock
on a Friday, and that is the owner's promise to make, not ours to make
for them. Set `response_time_note` in site details and it appears under
every enquiry form; leave it blank and the site promises nothing.

## Where each kind of content lives

| | Edited in | Why there |
|---|---|---|
| Page headings, prose, calls to action | **CMS → Pages** | Business wording. Changes without a deploy. |
| Service names, prices, descriptions, process, FAQs | **Services** | The public catalogue is built entirely from these rows. |
| Questions and answers, testimonials, team, navigation, social links | **CMS → shared lists** | Used by several pages at once. |
| Articles | **Blog** | |
| Company name, contact details, meta defaults, reply-time note | **CMS → Site details** | One place, so they cannot drift between pages. |
| Form labels, help text, empty states, button labels | **Code** | They describe what *this software* does. Moving them to the CMS would let them drift away from the behaviour they describe. |

That last row is the line worth holding. "What services do you offer?" is
business content. "Your enquiry is stored and goes straight to the team"
is a description of the code, and it should change when the code does.

## The pages a fresh install ships with

`home`, `about`, `services`, `contact` and `privacy`, seeded by
`cms/0007_seed_professional_content`. Every word is editable afterwards;
the migration decides only what the site says on day one.

The **services** page is unusual: it carries the slug `services`, which
the catalogue route claims first. So it is never reachable on its own
and cannot compete with the catalogue for the same search result. It
exists purely to make the catalogue's heading and introduction editable.

## Writing in a body field

Section bodies, service descriptions and articles all use the same
formatter (`apps/cms/richtext.py`): blank lines separate paragraphs, and
`## heading`, `- list`, `1. list`, `> quote`, `**bold**`, `*italic*` and
`[text](link)` all work. It escapes first and then emits a fixed set of
elements, so pasted HTML is shown as text rather than executed, and a
`javascript:` URL never reaches an `href`.

Lines inside a paragraph are joined, so wrapping your source at seventy
columns produces one paragraph rather than nine.

## Empty states

Every list has one, and each says three things: why the area is empty,
what will appear in it, and — where the reader can do something about
it — the action. `ui_empty_state` for a panel, `ui_table_empty` for a
table.

Two behaviours follow from this:

- **A section backed by an empty shared list is not rendered at all.** An
  editor who adds a testimonials section before writing any testimonials
  gets no section, rather than a heading with nothing underneath it.
- **A module that does not exist shows what it will hold.** The unbuilt
  sections (campaigns, SEO, paid ads, social, email marketing, analytics,
  approvals, subscriptions, media, integrations, audit, settings) declare
  their intended areas in `apps/staff/navigation.py` and list them on the
  placeholder page. They never show sample data: a dashboard that invents
  a plausible number during development is not trusted later, when the
  numbers matter.

## Client workspace

A newly registered client sees "Your workspace is ready", the areas that
will fill up, and two things they can usefully do now. No fabricated
campaign, no invented metric. The areas are declared in
`apps/organizations/views.py` beside the view that renders them.

## SEO

Every public page has a title, a meta description, Open Graph tags, a
canonical URL and exactly one `<h1>` — the last is asserted by a test,
because a second `<h1>` is the kind of thing that arrives with a new
section and is noticed by nobody.

Page sections carry an anchor derived from their heading, so
`/privacy/#cookies-and-tracking` lands where a reader expects. A test
walks every navigation link, follows any fragment, and fails if there is
nothing to land on.
