"""Turn a confirmed time into a calendar invite everyone can actually use.

An .ics file is the lowest-friction way to get a meeting onto other people's calendars:
no OAuth consent per person, no knowing anyone's email address, and it works with Google
Calendar, Apple Calendar and Outlook alike. Discord renders it as an attachment, so
confirming a time and adding it to your calendar is one click apart.

The same bytes are also what an emailed invite carries — switching `METHOD:PUBLISH` to
`REQUEST` and attaching this as `text/calendar` is exactly how Gmail produces an invite
with RSVP buttons, if that's ever wanted.
"""

import re
from datetime import UTC, datetime
from uuid import uuid4

_PRODID = "-//Agent-910//Meeting Scheduler//EN"
_MAX_OCTETS = 75  # RFC 5545 content lines are folded at 75 octets


def _escape(value: str) -> str:
    r"""Escape a TEXT value: backslash, semicolon and comma, and newlines as \n.

    Order matters — backslashes have to be escaped before the characters whose
    escapes introduce new backslashes.
    """
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;").replace(",", "\\,")
    return re.sub(r"\r\n|\r|\n", "\\\\n", value)


def _fold(line: str) -> str:
    """Wrap a long content line, continuing with a leading space.

    Folding is by octets rather than characters, so the encoded length is what's
    measured — otherwise a line of CJK text would fold far too late.
    """
    raw = line.encode()
    if len(raw) <= _MAX_OCTETS:
        return line

    chunks, start = [], 0
    limit = _MAX_OCTETS
    while start < len(raw):
        end = min(start + limit, len(raw))
        # Back off until `end` sits on a character boundary — that's any byte which
        # isn't a UTF-8 continuation byte (0b10xxxxxx) — so CJK text isn't split
        # mid-character.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode())
        start = end
        limit = _MAX_OCTETS - 1  # continuation lines lose one octet to the leading space
    return "\r\n ".join(chunks)


def _stamp(moment: datetime) -> str:
    """Format as a UTC timestamp, the form that needs no VTIMEZONE block."""
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_ics(
    *,
    start: datetime,
    end: datetime,
    summary: str,
    description: str = "",
    organizer: str = "",
) -> bytes:
    """Build a single-event calendar file.

    Args:
        start: When the meeting starts (timezone-aware).
        end: When it ends (timezone-aware).
        summary: The meeting title, as it appears in the calendar.
        description: Optional longer text, e.g. who confirmed it and why.
        organizer: Optional display name of whoever confirmed.

    Returns:
        The .ics file's bytes, ready to attach.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uuid4()}@agent-910",
        f"DTSTAMP:{_stamp(datetime.now(tz=UTC))}",
        f"DTSTART:{_stamp(start)}",
        f"DTEND:{_stamp(end)}",
        f"SUMMARY:{_escape(summary)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if organizer:
        lines.append(f"ORGANIZER;CN={_escape(organizer)}:MAILTO:noreply@agent-910.invalid")
    lines += ["END:VEVENT", "END:VCALENDAR"]

    # RFC 5545 requires CRLF line endings, including a trailing one.
    return ("\r\n".join(_fold(line) for line in lines) + "\r\n").encode()


def filename_for(summary: str) -> str:
    """A safe, recognizable .ics filename derived from the meeting title."""
    slug = re.sub(r"[^\w-]+", "-", summary, flags=re.UNICODE).strip("-")
    return f"{slug[:40] or 'meeting'}.ics"
