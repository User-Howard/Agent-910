"""Who is free when, as structured state rather than something re-read from chat.

The bot could in principle re-derive everyone's availability from the conversation on
every turn, but that makes it forgetful and vague: it can't tell "Bob hasn't answered"
apart from "Bob answered and I missed it", and a throwaway "還不確定" reads the same as a
firm commitment. So what people say gets parsed once and written down here, in SQLite.

Two things fall out of storing it properly. Answers accumulate across a conversation
instead of needing everyone to speak at once, and "not yet known" becomes a first-class
state — the bot can say who it's still waiting on rather than quietly computing an
overlap from half the group.
"""

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.settings import settings

_PATH = settings.data_dir / "meetings.db"

GRAIN = timedelta(minutes=30)
"""Resolution of the slot grid. Everything is rounded to this."""

DAY_START, DAY_END = 8, 23
"""Waking hours, in local time, that any stated window is clipped to.

Open-ended answers are the reason this exists. "我週三 2 點後不行" is genuinely a
statement about being free *before* 14:00, and the honest reading of its start is
midnight — which then fills the chart with small hours nobody would meet in, and
pushes the real afternoon options off the bottom of it.
"""

STALE_AFTER = timedelta(days=7)
"""How long an unsettled meeting stays the channel's "current" one.

Without this, a scheduling attempt that fizzled out weeks ago would quietly capture
the next one in that channel, and everyone's long-expired answers would come back
with it. Past this age the bot starts a fresh meeting instead.
"""

# What we know about one person. Only STATED feeds the overlap; the rest exist so the
# bot can tell "no" apart from "not yet" apart from "maybe".
PENDING = "pending"  # named as a participant, hasn't said anything
STATED = "stated"  # gave concrete times
TENTATIVE = "tentative"  # said something real but non-committal ("還不確定", "看情況")
UNAVAILABLE = "unavailable"  # can't make it at all

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    settled_start TEXT,
    settled_by TEXT
);
CREATE INDEX IF NOT EXISTS meetings_channel ON meetings (channel_id, id);

CREATE TABLE IF NOT EXISTS responses (
    meeting_id INTEGER NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    person TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (meeting_id, person)
);

CREATE TABLE IF NOT EXISTS windows (
    meeting_id INTEGER NOT NULL,
    person TEXT NOT NULL,
    start_utc TEXT NOT NULL,
    end_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS windows_lookup ON windows (meeting_id, person);
"""


def _connect() -> sqlite3.Connection:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def _local(moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(settings.timezone))


@dataclass(frozen=True)
class Window:
    """A stretch of time someone said they're free."""

    start: datetime
    end: datetime

    def covers(self, start: datetime, duration: timedelta) -> bool:
        return self.start <= start and start + duration <= self.end

    def label(self) -> str:
        start, end = _local(self.start), _local(self.end)
        same_day = start.date() == end.date()
        tail = f"{end:%H:%M}" if same_day else f"{end:%m/%d %H:%M}"
        return f"{start:%m/%d} ({start:%a}) {start:%H:%M}-{tail}"


def clip_to_waking_hours(window: Window) -> Window | None:
    """Trim a window to DAY_START..DAY_END, or drop it if nothing is left.

    Clipping each end against its own local date, so a window that legitimately spans
    days keeps its middle.
    """
    start, end = _local(window.start), _local(window.end)
    earliest = start.replace(hour=DAY_START, minute=0, second=0, microsecond=0)
    latest = end.replace(hour=DAY_END, minute=0, second=0, microsecond=0)
    start, end = max(start, earliest), min(end, latest)
    return Window(start=start, end=end) if end > start else None


@dataclass
class Response:
    """Everything known about one person for one meeting."""

    person: str
    status: str
    note: str = ""
    windows: list[Window] = field(default_factory=list)

    def summary(self) -> str:
        if self.status == STATED and self.windows:
            return f"{self.person}: " + "; ".join(w.label() for w in self.windows)
        wording = {
            PENDING: "hasn't answered yet",
            TENTATIVE: "not committed yet",
            UNAVAILABLE: "can't make it",
            STATED: "said yes but gave no times",
        }[self.status]
        return f"{self.person}: {wording}" + (f" ({self.note})" if self.note else "")


@dataclass
class Meeting:
    id: int
    topic: str
    duration_minutes: int
    settled_start: datetime | None = None
    settled_by: str | None = None


def open_meeting(channel_id: int, topic: str, duration_minutes: int) -> Meeting:
    """Start tracking a meeting in this channel, or return the one already open.

    Only one meeting is tracked per channel at a time — a channel discussing two
    meetings at once is rare enough that guessing which one a reply belongs to would
    cause more errors than it prevents.
    """
    existing = current_meeting(channel_id)
    if existing is not None:
        return existing

    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO meetings (channel_id, topic, duration_minutes, created_at) "
            "VALUES (?, ?, ?, ?)",
            (channel_id, topic, duration_minutes, datetime.now(tz=UTC).isoformat()),
        )
        return Meeting(id=cursor.lastrowid, topic=topic, duration_minutes=duration_minutes)


def current_meeting(channel_id: int) -> Meeting | None:
    """The channel's most recent meeting that nobody has settled on a time for yet."""
    cutoff = (datetime.now(tz=UTC) - STALE_AFTER).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM meetings WHERE channel_id = ? AND settled_start IS NULL "
            "AND created_at >= ? ORDER BY id DESC LIMIT 1",
            (channel_id, cutoff),
        ).fetchone()
    if row is None:
        return None
    return Meeting(id=row["id"], topic=row["topic"], duration_minutes=row["duration_minutes"])


def retopic(meeting_id: int, topic: str, duration_minutes: int) -> None:
    """Correct the topic or length once the conversation makes them clearer."""
    with _connect() as conn:
        conn.execute(
            "UPDATE meetings SET topic = ?, duration_minutes = ? WHERE id = ?",
            (topic, duration_minutes, meeting_id),
        )


def settle(meeting_id: int, start: datetime, by: str) -> None:
    """Record the agreed time, which closes the meeting to further answers."""
    with _connect() as conn:
        conn.execute(
            "UPDATE meetings SET settled_start = ?, settled_by = ? WHERE id = ?",
            (start.astimezone(UTC).isoformat(), by, meeting_id),
        )


def note_participants(meeting_id: int, people: list[str]) -> None:
    """Mark people as expected to answer, without overwriting anyone who already has."""
    now = datetime.now(tz=UTC).isoformat()
    with _connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO responses (meeting_id, person, status, updated_at) "
            "VALUES (?, ?, ?, ?)",
            [(meeting_id, person, PENDING, now) for person in people],
        )


def record(
    meeting_id: int,
    person: str,
    status: str,
    windows: list[Window] | None = None,
    note: str = "",
) -> None:
    """Save what one person said, replacing anything they said before.

    Replacing rather than appending is deliberate: when someone revises ("啊週三不行
    了"), their latest message is the truth, and merging it with the old one would
    silently keep a time they just withdrew.
    """
    now = datetime.now(tz=UTC).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO responses (meeting_id, person, status, note, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (meeting_id, person) "
            "DO UPDATE SET status = excluded.status, note = excluded.note, "
            "updated_at = excluded.updated_at",
            (meeting_id, person, status, note, now),
        )
        conn.execute(
            "DELETE FROM windows WHERE meeting_id = ? AND person = ?", (meeting_id, person)
        )
        clipped = [c for w in windows or [] if (c := clip_to_waking_hours(w)) is not None]
        conn.executemany(
            "INSERT INTO windows (meeting_id, person, start_utc, end_utc) VALUES (?, ?, ?, ?)",
            [
                (meeting_id, person, w.start.astimezone(UTC).isoformat(), w.end.astimezone(UTC).isoformat())
                for w in clipped
            ],
        )


def responses(meeting_id: int) -> list[Response]:
    """Everyone on record for this meeting, those who answered first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM responses WHERE meeting_id = ? ORDER BY status = ? , person",
            (meeting_id, PENDING),
        ).fetchall()
        windows = conn.execute(
            "SELECT * FROM windows WHERE meeting_id = ? ORDER BY start_utc", (meeting_id,)
        ).fetchall()

    by_person: dict[str, list[Window]] = {}
    for row in windows:
        by_person.setdefault(row["person"], []).append(
            Window(
                start=datetime.fromisoformat(row["start_utc"]),
                end=datetime.fromisoformat(row["end_utc"]),
            )
        )
    return [
        Response(
            person=row["person"],
            status=row["status"],
            note=row["note"],
            windows=by_person.get(row["person"], []),
        )
        for row in rows
    ]


@dataclass
class Slot:
    """One candidate meeting time, and who can make it."""

    start: datetime
    end: datetime
    who: list[str]

    def label(self) -> str:
        start, end = _local(self.start), _local(self.end)
        return f"{start:%m/%d} ({start:%a}) {start:%H:%M}-{end:%H:%M}"


def _grid(answered: list[Response], duration: timedelta) -> list[Slot]:
    """Every start time on the half-hour that at least one person can make.

    Nothing in the past is offered. Answers outlive the moment they were given — one
    said on Monday about "Wednesday" is still on file the following Friday — so
    without this the bot would cheerfully propose a meeting that has already happened.
    """
    now = datetime.now(tz=UTC)
    all_windows = [w for r in answered for w in r.windows if w.end > now]
    if not all_windows:
        return []

    # Start the grid on a clean half-hour so columns line up between people, and never
    # before now.
    first = max(min(w.start for w in all_windows), now)
    epoch = first.replace(minute=0 if first.minute < 30 else 30, second=0, microsecond=0)
    if epoch < now:  # rounding down must not step back into the past
        epoch += GRAIN
    last = max(w.end for w in all_windows)

    slots: list[Slot] = []
    start = epoch
    while start + duration <= last:
        who = [r.person for r in answered if any(w.covers(start, duration) for w in r.windows)]
        if who:
            slots.append(Slot(start=start, end=start + duration, who=who))
        start += GRAIN
    return slots


def overlap(meeting_id: int) -> tuple[list[Slot], list[Response]]:
    """Work out when people can meet, given everything said so far.

    Returns:
        Candidate slots (any with at least one taker, best-attended first is *not*
        applied — they stay in time order), and the full response list including
        whoever hasn't answered.
    """
    everyone = responses(meeting_id)
    answered = [r for r in everyone if r.status == STATED and r.windows]
    with _connect() as conn:
        row = conn.execute(
            "SELECT duration_minutes FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
    duration = timedelta(minutes=row["duration_minutes"] if row else settings.default_meeting_minutes)
    return _grid(answered, duration), everyone


def unanimous(slots: list[Slot], answered_count: int) -> list[Slot]:
    """Just the slots everyone who answered can make."""
    return [s for s in slots if len(s.who) == answered_count and answered_count > 0]


def describe(meeting_id: int) -> str:
    """Plain-text state of play, for the model to reason over.

    Deliberately spells out who hasn't answered — that's the fact most likely to
    change what the bot should do next, and the easiest one to lose.
    """
    slots, everyone = overlap(meeting_id)
    answered = [r for r in everyone if r.status == STATED and r.windows]
    waiting = [r for r in everyone if r.status == PENDING]
    lines = [r.summary() for r in everyone]

    best = unanimous(slots, len(answered))
    if best:
        merged = merge(best)
        lines.append(
            f"All {len(answered)} who answered can make: "
            + "; ".join(s.label() for s in merged[:6])
        )
    elif slots:
        top = max(len(s.who) for s in slots)
        picks = [s for s in slots if len(s.who) == top][:4]
        lines.append(
            f"Nothing works for all {len(answered)}. Best is {top} of them: "
            + "; ".join(f"{s.label()} ({', '.join(s.who)})" for s in picks)
        )
    else:
        lines.append("No times to compare yet.")

    if waiting:
        lines.append(f"Still waiting on: {', '.join(r.person for r in waiting)}")
    return "\n".join(lines)


def merge(slots: list[Slot]) -> list[Slot]:
    """Collapse back-to-back slots with the same people into single stretches."""
    merged: list[Slot] = []
    for slot in sorted(slots, key=lambda s: s.start):
        last = merged[-1] if merged else None
        if last and slot.start <= last.end and set(slot.who) == set(last.who):
            merged[-1] = Slot(start=last.start, end=max(last.end, slot.end), who=last.who)
        else:
            merged.append(slot)
    return merged


# Shading runs densest-first; a slot's level is picked by what fraction of the people
# who answered can make it, so partial overlap stays visible instead of collapsing to
# "not everyone, therefore no".
_LEVELS = [(1.0, "██"), (0.66, "▓▓"), (0.33, "▒▒"), (0.0, "░░")]
_EMPTY = "··"
_CELL = 6
_LABEL = 6
_MAX_DAYS = 7
_MAX_ROWS = 24


def render_heatmap(meeting_id: int) -> str:
    """Draw a when2meet-style grid of who can make what.

    Days across the top, times down the side, each cell shaded by how many of the
    people who answered are free then. Rows where nobody is free are dropped, so a
    fortnight's worth of options stays a handful of lines.

    Returns:
        A Discord code block, ready to post as-is.
    """
    slots, everyone = overlap(meeting_id)
    answered = [r for r in everyone if r.status == STATED and r.windows]
    if not slots or not answered:
        waiting = [r.person for r in everyone if r.status == PENDING]
        missing = f" Waiting on: {', '.join(waiting)}." if waiting else ""
        return f"```\n(nobody has given times yet){missing}\n```"

    marks: dict[tuple, str] = {}
    for slot in slots:
        local = _local(slot.start)
        share = len(slot.who) / len(answered)
        marks[(local.date(), local.time())] = next(m for cut, m in _LEVELS if share >= cut)

    days = sorted({d for d, _ in marks})[:_MAX_DAYS]
    times = sorted({t for d, t in marks if d in days})
    if len(times) > _MAX_ROWS:
        # Coarsen to whole hours rather than truncating. Cutting the list short would
        # silently drop the *end* of the day, which is where the best slots usually
        # are; halving the resolution keeps the whole span visible.
        hourly = [t for t in times if t.minute == 0]
        times = (hourly or times)[:_MAX_ROWS]
        coarse = True
    else:
        coarse = False

    header = " " * _LABEL + "".join(f"{d:%m/%d}".center(_CELL) for d in days)
    weekdays = " " * _LABEL + "".join(f"{d:%a}".center(_CELL) for d in days)
    rows = [
        f"{t:%H:%M}".ljust(_LABEL)
        + "".join(marks.get((d, t), _EMPTY).center(_CELL) for d in days)
        for t in times
    ]

    counts = Counter(len(s.who) for s in slots)
    legend = "  ".join(
        f"{next(m for cut, m in _LEVELS if n / len(answered) >= cut)} {n}/{len(answered)}"
        for n in sorted(counts, reverse=True)
    )
    lines = [
        f"{describe_meeting(meeting_id)} - {settings.timezone}",
        "",
        header,
        weekdays,
        *rows,
        "",
        legend,
    ]
    if coarse:
        lines.append("(shown hourly)")
    waiting = [r.person for r in everyone if r.status == PENDING]
    if waiting:
        lines.append(f"not in yet: {', '.join(waiting)}")
    if len({_local(s.start).date() for s in slots}) > _MAX_DAYS:
        lines.append(f"(first {_MAX_DAYS} days shown)")
    return "```\n" + "\n".join(lines) + "\n```"


def describe_meeting(meeting_id: int) -> str:
    """Short "topic (60 min)" heading."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT topic, duration_minutes FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
    return f"{row['topic']} ({row['duration_minutes']} min)" if row else "Meeting"
