"""A small, safe formatter for blog content.

Posts are stored as plain text and rendered here. The alternative — a
rich-text editor storing HTML — means either trusting whatever markup
reaches the database or running a sanitiser, and both are a standing
risk for a field that staff paste into from elsewhere.

So: **escape first, then format**. Nothing an author types can become
markup; only the patterns below are turned into HTML, and they are turned
into a fixed set of elements the design system styles. A dependency-free
subset of Markdown, chosen for what a marketing post actually needs:

    ## Heading
    ### Smaller heading
    - a list item
    1. a numbered item
    > a pulled quote
    **bold** and *italic*
    [link text](https://example.com)

Blank lines separate paragraphs. Link schemes are checked, so a
`javascript:` URL cannot be smuggled in through the one place markup is
produced.
"""

from __future__ import annotations

import re

from django.utils.html import escape
from django.utils.safestring import mark_safe

#: Schemes a link may use. Anything else is rendered as plain text, so a
#: `javascript:` or `data:` URL never reaches an href.
SAFE_SCHEMES = ("http://", "https://", "mailto:", "tel:")

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _is_safe_url(url: str) -> bool:
    lowered = url.strip().lower()
    if lowered.startswith("/") or lowered.startswith("#"):
        return True
    return lowered.startswith(SAFE_SCHEMES)


def _inline(text: str) -> str:
    """Inline formatting, applied to already-escaped text."""

    def link(match: re.Match) -> str:
        label, url = match.group(1), match.group(2)
        if not _is_safe_url(url):
            # Render the author's text, drop the destination. Silently
            # producing a link to a scheme we do not trust would be worse.
            return label
        # An external link opens in a new tab, with rel="noopener" so the
        # opened page cannot reach back through window.opener.
        external = url.startswith(("http://", "https://"))
        attributes = ' target="_blank" rel="noopener"' if external else ""
        return (f'<a href="{url}"{attributes} '
                f'class="text-gold-600 underline underline-offset-2">{label}</a>')

    text = _LINK.sub(link, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    return _ITALIC.sub(r"<em>\1</em>", text)


def render(content: str) -> str:
    """Turn stored post text into HTML.

    Returns a safe string: the input was escaped before any markup was
    produced, so the only tags present are the ones this function emits.
    """
    if not content:
        return mark_safe("")  # noqa: S308 - empty string

    blocks: list[str] = []
    list_items: list[str] = []
    list_kind = ""
    paragraph: list[str] = []

    def flush_list() -> None:
        nonlocal list_items, list_kind
        if list_items:
            tag = "ol" if list_kind == "ordered" else "ul"
            css = ("list-decimal" if list_kind == "ordered" else "list-disc")
            items = "".join(f"<li>{item}</li>" for item in list_items)
            blocks.append(
                f'<{tag} class="{css} space-y-2 pl-5 text-steel">{items}</{tag}>'
            )
            list_items = []
            list_kind = ""

    def flush_paragraph() -> None:
        """Emit the plain lines gathered so far as one paragraph.

        Consecutive lines are joined rather than each becoming its own
        `<p>`. An author who wraps their source at seventy columns — or
        writes in an editor that soft-wraps for them — means one
        paragraph, not nine; and formatting that opens on one line and
        closes on the next has to see both halves to match at all.
        """
        nonlocal paragraph
        if paragraph:
            blocks.append(
                '<p class="text-base leading-relaxed text-steel">'
                f'{_inline(" ".join(paragraph))}</p>'
            )
            paragraph = []

    def flush() -> None:
        flush_paragraph()
        flush_list()

    for raw_block in escape(content).replace("\r\n", "\n").split("\n\n"):
        block = raw_block.strip("\n")
        if not block.strip():
            continue

        for line in block.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("### "):
                flush()
                blocks.append(
                    '<h3 class="mt-8 text-xl font-semibold text-navy">'
                    f"{_inline(stripped[4:])}</h3>"
                )
            elif stripped.startswith("## "):
                flush()
                blocks.append(
                    '<h2 class="mt-10 text-2xl font-semibold tracking-tight text-navy">'
                    f"{_inline(stripped[3:])}</h2>"
                )
            elif stripped.startswith("&gt; "):
                # `>` was escaped on the way in.
                flush()
                blocks.append(
                    '<blockquote class="border-l-2 border-gold pl-4 text-lg '
                    f'italic text-navy">{_inline(stripped[5:])}</blockquote>'
                )
            elif stripped.startswith("- "):
                flush_paragraph()
                if list_kind != "unordered":
                    flush_list()
                    list_kind = "unordered"
                list_items.append(_inline(stripped[2:]))
            elif re.match(r"^\d+\.\s", stripped):
                flush_paragraph()
                if list_kind != "ordered":
                    flush_list()
                    list_kind = "ordered"
                list_items.append(_inline(re.sub(r"^\d+\.\s", "", stripped)))
            else:
                flush_list()
                paragraph.append(stripped)

        # A blank line ended the block, so it ends the paragraph too.
        flush_paragraph()

    flush()
    return mark_safe("".join(blocks))  # noqa: S308 - built from escaped input


def plain_text(content: str) -> str:
    """The post with its formatting markers removed.

    Used for the excerpt fallback and the reading-time count, where the
    syntax characters would otherwise be counted as words.
    """
    text = _LINK.sub(r"\1", content or "")
    text = re.sub(r"[*>#]+", "", text)
    text = re.sub(r"^\s*[-\d]+\.?\s", "", text, flags=re.MULTILINE)
    return " ".join(text.split())


def reading_minutes(content: str) -> int:
    """Rounded up, never zero — "0 min read" reads like a bug."""
    words = len(plain_text(content).split())
    return max(1, round(words / 200))
