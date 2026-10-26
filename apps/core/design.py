"""Design-system vocabulary.

Variant-to-class mapping lives here, not in `{% if %}` chains inside
templates and not scattered through views. One place to change a brand
decision, and the mapping can be unit-tested without rendering anything.

Every lookup falls back to a defined default rather than returning an
empty string: a typo in a template should produce a plain component, not
an unstyled one.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

BUTTON_BASE = (
    "inline-flex items-center justify-center gap-2 rounded-[var(--radius-control)] "
    "font-semibold transition focus-ring "
    "disabled:cursor-not-allowed disabled:opacity-50"
)

BUTTON_VARIANTS = {
    "primary": "bg-gold text-navy hover:bg-gold-600",
    "secondary": "bg-navy text-white hover:bg-navy-600",
    "outline": "border border-steel-200 bg-white text-navy hover:bg-mist",
    "ghost": "text-navy hover:bg-mist",
    "subtle": "bg-mist text-navy hover:bg-steel-200",
    "danger": "bg-danger text-white hover:opacity-90",
}

BUTTON_SIZES = {
    "sm": "px-3 py-1.5 text-xs",
    "md": "px-4 py-2 text-sm",
    "lg": "px-5 py-2.5 text-base",
}

ICON_BUTTON_SIZES = {
    "sm": "h-7 w-7",
    "md": "h-9 w-9",
    "lg": "h-11 w-11",
}

# ---------------------------------------------------------------------------
# Status vocabulary
#
# The campaign states in the product reference are Live / Paused / Planned /
# Done. Keeping their colours in one map means a status reads the same on a
# badge, a table row and a card.
# ---------------------------------------------------------------------------

BADGE_TONES = {
    "neutral": "bg-mist text-steel",
    "gold": "bg-gold-50 text-gold-600",
    "live": "bg-live-soft text-live",
    "paused": "bg-paused-soft text-paused",
    "planned": "bg-planned-soft text-planned",
    "done": "bg-done-soft text-done",
    "danger": "bg-danger-soft text-danger",
    "info": "bg-done-soft text-done",
}

STATUS_TONES = {
    "live": "live",
    "active": "live",
    "approved": "live",
    "published": "live",
    "paused": "paused",
    "pending": "paused",
    "awaiting_approval": "paused",
    "draft": "neutral",
    "planned": "planned",
    "scheduled": "planned",
    "done": "done",
    "completed": "done",
    "closed": "done",
    "cancelled": "danger",
    "rejected": "danger",
    "overdue": "danger",
    "failed": "danger",

    # Pipeline stages, for leads and quote requests. Read as a
    # temperature rather than a traffic light: "planned" is work that has
    # arrived, "paused" is work waiting on somebody else, "live" is a
    # good outcome and "danger" is a lost one. Without these every stage
    # rendered the same grey, which made a pipeline impossible to scan.
    "new": "planned",
    "contacted": "planned",
    "qualified": "planned",
    "reviewing": "planned",
    "proposal": "paused",
    "clarification_required": "paused",
    "proposal_ready": "live",
    "accepted": "live",
    "won": "live",
    "declined": "danger",
    "lost": "danger",
    "archived": "neutral",

    # Integration connection and sync-run statuses.
    "connected": "live",
    "not_configured": "neutral",
    "needs_reauthorization": "paused",
    "disconnected": "neutral",
    "running": "planned",
    "success": "live",
    "partial": "paused",
    "skipped": "neutral",
    "error": "danger",
}

ALERT_TONES = {
    "info": "border-steel-200 bg-mist text-navy",
    "success": "border-live bg-live-soft text-live",
    "warning": "border-paused bg-paused-soft text-paused",
    "danger": "border-danger bg-danger-soft text-danger",
    # Django's messages framework emits `error` and `debug`; mapping them
    # here stops a real message silently rendering as "info".
    "error": "border-danger bg-danger-soft text-danger",
    "debug": "border-steel-200 bg-mist text-steel",
}

ALERT_ROLES = {
    "danger": "alert",
    "error": "alert",
    "warning": "alert",
    "info": "status",
    "success": "status",
    "debug": "status",
}

# ---------------------------------------------------------------------------
# Metrics
#
# Direction is always chosen by the caller. A falling cost per lead is good
# news and falling revenue is not, so the component must never infer tone
# from the sign of the number.
# ---------------------------------------------------------------------------

DELTA_DIRECTIONS = {
    "up": ("text-live", "↑"),
    "down": ("text-danger", "↓"),
    "flat": ("text-steel", "→"),
    "good": ("text-live", ""),
    "bad": ("text-danger", ""),
    "neutral": ("text-steel", ""),
}

ALIGNMENTS = {
    "left": "text-left",
    "center": "text-center",
    "right": "text-right",
}

DRAWER_SIDES = {
    "right": "right-0 top-0 h-full",
    "left": "left-0 top-0 h-full",
    "bottom": "bottom-0 left-0 w-full",
}

DRAWER_TRANSITIONS = {
    "right": ("translate-x-full", "translate-x-0"),
    "left": ("-translate-x-full", "translate-x-0"),
    "bottom": ("translate-y-full", "translate-y-0"),
}

MODAL_SIZES = {
    "sm": "max-w-sm",
    "md": "max-w-lg",
    "lg": "max-w-2xl",
    "xl": "max-w-4xl",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def classes(*parts: Any) -> str:
    """Join class fragments, dropping anything empty."""
    return " ".join(str(part).strip() for part in parts if part)


def button_classes(variant: str = "primary", size: str = "md", *,
                   full: bool = False, icon_only: bool = False) -> str:
    size_css = ICON_BUTTON_SIZES.get(size, ICON_BUTTON_SIZES["md"]) if icon_only \
        else BUTTON_SIZES.get(size, BUTTON_SIZES["md"])
    return classes(
        BUTTON_BASE,
        BUTTON_VARIANTS.get(variant, BUTTON_VARIANTS["primary"]),
        size_css,
        "p-0" if icon_only else "",
        "w-full" if full else "",
    )


def badge_tone(tone: str) -> str:
    return BADGE_TONES.get(tone, BADGE_TONES["neutral"])


def tone_for_status(status: Any) -> str:
    """Map a domain status onto a badge tone.

    Accepts whatever the caller has — a TextChoices member, a raw string,
    None — so a template never has to normalise before asking.
    """
    if status is None:
        return "neutral"
    key = str(getattr(status, "value", status)).strip().lower().replace(" ", "_")
    return STATUS_TONES.get(key, "neutral")


def status_label(status: Any) -> str:
    """A human-readable label for a status value.

    A TextChoices member already carries one. A raw string does not, and
    rendering `awaiting_approval` on a badge is not something to put in
    front of a client, so it is humanised.
    """
    if status is None:
        return "Unknown"

    label = getattr(status, "label", None)
    if label:
        return str(label)

    text = str(status).strip().replace("_", " ").replace("-", " ")
    return text[:1].upper() + text[1:] if text else "Unknown"


def alert_tone(tone: str) -> tuple[str, str]:
    """Return (css, aria role) for an alert tone."""
    key = str(tone or "info").lower()
    return ALERT_TONES.get(key, ALERT_TONES["info"]), ALERT_ROLES.get(key, "status")


def delta_style(direction: str) -> tuple[str, str]:
    return DELTA_DIRECTIONS.get(direction, DELTA_DIRECTIONS["flat"])


def percentage(current: Any, target: Any) -> float:
    """Clamped completion percentage, safe against bad input.

    Exceeding a goal is good news, not a bar overflowing its track, so the
    result is capped at 100.
    """
    try:
        value = (float(current) / float(target)) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0
    return round(min(100.0, max(0.0, value)), 1)
