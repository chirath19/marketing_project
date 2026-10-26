"""Chat layout flags shared by the client conversation and quote threads."""

from django.utils import timezone

#: Messages from one person this close together share a bubble group.
GROUP_SECONDS = 300


def group(entries):
    """Mark day breaks, the first unread entry, and where a sender's run starts.

    Entries are oldest first and need `created_at`, `sender_id` and
    `was_unread`. An entry with `is_event` set always stands alone.
    """
    previous = None
    first_unread_seen = False
    for entry in entries:
        entry.sender_label = (
            entry.sender.get_full_name() or entry.sender.email
        ) if entry.sender else ""
        entry.first_unread = entry.was_unread and not first_unread_seen
        first_unread_seen = first_unread_seen or entry.was_unread
        entry.new_day = previous is None or (
            timezone.localdate(previous.created_at) != timezone.localdate(entry.created_at)
        )
        entry.starts_group = (
            entry.new_day
            or entry.first_unread
            or getattr(previous, "is_event", False)
            or getattr(previous, "is_internal", False) != getattr(entry, "is_internal", False)
            or previous.sender_id != entry.sender_id
            or (entry.created_at - previous.created_at).total_seconds() > GROUP_SECONDS
        )
        previous = entry
    return entries
