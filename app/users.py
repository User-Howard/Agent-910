"""Discord user contact details the bot can reuse across meetings."""

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from app.settings import settings

_PATH = settings.data_dir / "users.db"
_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_gmails (
    discord_user_id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    gmail TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS user_gmails_display_name ON user_gmails (display_name);
"""


@dataclass(frozen=True)
class GmailRecord:
    discord_user_id: int
    display_name: str
    gmail: str


def _connect() -> sqlite3.Connection:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def normalize_gmail(value: str) -> str:
    """Return a canonical Google Calendar email address, or raise if invalid."""
    gmail = value.strip().lower()
    if not _EMAIL_RE.fullmatch(gmail):
        raise ValueError("Please use a valid email address, like name@company.edu.tw.")
    return gmail


def save_gmail(discord_user_id: int, display_name: str, gmail: str) -> GmailRecord:
    """Remember the Google Calendar email a Discord user wants invites sent to."""
    normalized = normalize_gmail(gmail)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO user_gmails (discord_user_id, display_name, gmail, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (discord_user_id) DO UPDATE SET "
            "display_name = excluded.display_name, gmail = excluded.gmail, "
            "updated_at = excluded.updated_at",
            (discord_user_id, display_name, normalized, datetime.now(tz=UTC).isoformat()),
        )
    return GmailRecord(discord_user_id=discord_user_id, display_name=display_name, gmail=normalized)


def forget_gmail(discord_user_id: int) -> bool:
    """Delete a Discord user's saved Google Calendar email address."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM user_gmails WHERE discord_user_id = ?", (discord_user_id,)
        )
    return cursor.rowcount > 0


def gmail_for_discord_user(discord_user_id: int) -> GmailRecord | None:
    """Look up one Discord user's saved Google Calendar email address."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM user_gmails WHERE discord_user_id = ?", (discord_user_id,)
        ).fetchone()
    if row is None:
        return None
    return GmailRecord(
        discord_user_id=row["discord_user_id"],
        display_name=row["display_name"],
        gmail=row["gmail"],
    )


def gmail_for_display_names(names: list[str]) -> dict[str, GmailRecord]:
    """Find invite emails for meeting participants, keyed by display name.

    Scheduling state stores human display names because the LLM reads chat text.
    At invite time this best-effort lookup connects those names back to registered
    Google Calendar emails. Slash commands refresh display names whenever people register.
    """
    wanted = {name.casefold(): name for name in names}
    wanted.update({name.removeprefix("@").casefold(): name for name in names})
    if not wanted:
        return {}

    with _connect() as conn:
        rows = conn.execute("SELECT * FROM user_gmails").fetchall()

    matches: dict[str, GmailRecord] = {}
    for row in rows:
        original = wanted.get(row["display_name"].casefold())
        if original is None:
            continue
        matches[original] = GmailRecord(
            discord_user_id=row["discord_user_id"],
            display_name=row["display_name"],
            gmail=row["gmail"],
        )
    return matches
