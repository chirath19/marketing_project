"""Spam checks for public forms.

Layered, and deliberately **flagging rather than rejecting**. A
submission that trips a heuristic is still written to the database and
still appears in the Inbox under a spam filter, because the cost of a
false positive — losing somebody a client, silently — is far higher than
the cost of a staff member skimming past an obvious advert.

Outright rejection is reserved for the honeypot, which a person cannot
trip by accident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A human takes longer than this to read a form and fill it in. A script
#: submits immediately.
MINIMUM_SECONDS = 2.0

#: More links than this in a short message is advertising, not an enquiry.
MAX_LINKS = 3

_LINK = re.compile(r"https?://|www\.", re.IGNORECASE)

#: Phrases that are not what someone asking about marketing writes.
SPAM_PHRASES = (
    "seo services at cheap", "buy backlinks", "cheap viagra", "crypto investment",
    "guest post opportunity", "casino", "loan offer", "work from home scheme",
)


@dataclass(frozen=True, slots=True)
class Verdict:
    is_spam: bool
    reason: str = ""


def classify(*, message: str, name: str = "", elapsed_seconds: float | None = None,
             link_budget: int = MAX_LINKS) -> Verdict:
    """Decide whether a submission looks automated.

    Each check names itself in the reason, so a staff member rescuing a
    false positive can see which rule fired and the rule can be loosened
    rather than guessed at.
    """
    text = (message or "").lower()

    if elapsed_seconds is not None and elapsed_seconds < MINIMUM_SECONDS:
        return Verdict(True, "Submitted faster than a person can type")

    links = len(_LINK.findall(message or ""))
    if links > link_budget:
        return Verdict(True, f"Contains {links} links")

    for phrase in SPAM_PHRASES:
        if phrase in text:
            return Verdict(True, f"Contains “{phrase}”")

    if name and name.lower() in {"test", "asdf", "qwerty"} and len(text) < 20:
        return Verdict(True, "Looks like a test submission")

    return Verdict(False)
