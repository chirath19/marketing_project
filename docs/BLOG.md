# Blog

## Models

| | |
|---|---|
| `BlogPost` | title, slug, excerpt, content, featured image + alt, author, category, tags, status, publication date, SEO title, meta description |
| `Category` | One per post. Name, slug, description, order, visibility |
| `Tag` | Many per post. Name, slug, visibility |

Derived on the model, not duplicated in templates: `summary` (excerpt, or
the opening of the post), `reading_minutes`, `byline`, `is_published`,
`is_scheduled`, `body_html`.

## Content is plain text, not HTML

A rich-text editor storing HTML means either trusting whatever markup
reaches the database or running a sanitiser on every read. Instead posts
are stored as plain text and rendered by `apps/cms/richtext.py`, which
**escapes first and then formats** — so nothing an author types can become
markup, and only a fixed set of elements is ever produced.

```
## Heading          ### Smaller heading
- a list item       1. a numbered item
> a pulled quote    **bold** and *italic*
[link text](https://example.com)
```

Link schemes are checked, so `javascript:` and `data:` URLs are rendered
as plain text rather than reaching an `href`. External links get
`rel="noopener"`. 27 tests cover the formatter, most of them about what it
refuses to do.

## Scheduling

A `published_at` in the future holds the post back until that moment — a
post written on Monday appears on Thursday with nobody having to remember.
Unpublishing and republishing **keeps the original date**, so fixing a typo
does not move an old post to the top of the listing.

## Permissions

`blog_view` · `blog_create` · `blog_edit` · `blog_publish` · `blog_delete`

Separate from the `cms_*` rights: writing articles and editing marketing
pages are different jobs, often different people, and an agency should be
able to grant one without the other. A test asserts CMS permissions alone
do not open the blog.

The author is recorded once, on creation, and **never overwritten** — a
colleague fixing a typo does not take the byline.

## Public pages

| | |
|---|---|
| `/blog/` | Listing, 12 per page |
| `/blog/<slug>/` | Post |
| `/blog/category/<slug>/` | Category filter |
| `/blog/tag/<slug>/` | Tag filter |
| `/blog/feed/` | RSS |

**Related posts** come from the same category first, topped up from shared
tags. Never the post itself, never a draft.

Empty categories are not offered in the filter — a category page with
nothing on it is a dead end for a visitor and a thin page for a crawler.

## SEO

Per-post title and description with a fallback chain (meta → excerpt →
opening of the post), `BlogPosting` structured data with the author and
dates, Open Graph using the featured image, posts and categories in
`sitemap.xml`, an RSS feed advertised with `<link rel="alternate">`.

**Page two is canonical to itself**, with `rel="prev"` / `rel="next"` —
pointing every page at page one tells a crawler they are the same page and
the rest never get indexed.

## Two things it refuses to do

- **Publish a draft to anyone.** A draft is a 404 for signed-in staff too.
  Previewing is a separate surface, not a logged-in visitor seeing more.
- **Put a staff email on the public site.** `byline` uses the author's name
  and nothing else — `get_full_name()` falls back to the email address,
  which would publish it.
