"""Shared calendar side effects for confirmed meetings."""

import asyncio
import io
from dataclasses import dataclass
from datetime import datetime

import discord

from app import availability
from app.google_calendar import CalendarConfigError, create_event, is_configured
from app.invite import build_ics, filename_for
from app.users import gmail_for_display_names


@dataclass(frozen=True)
class CalendarDelivery:
    note: str
    ics: bytes
    filename: str

    def discord_file(self) -> discord.File:
        return discord.File(io.BytesIO(self.ics), filename=self.filename)


async def prepare_calendar_delivery(
    *,
    meeting_id: int | None,
    start: datetime,
    end: datetime,
    topic: str,
    description: str,
    organizer: str,
) -> CalendarDelivery:
    """Create Google Calendar invite when possible, and always prepare an .ics file."""
    ics = build_ics(
        start=start,
        end=end,
        summary=topic,
        description=description,
        organizer=organizer,
    )
    note = ""
    if meeting_id is not None:
        participant_names = [r.person for r in availability.responses(meeting_id)]
        gmails = gmail_for_display_names(participant_names)
        missing = sorted(set(participant_names) - set(gmails))
        if not is_configured():
            note = "\nGoogle Calendar event was not created because OAuth is not configured."
        elif not gmails:
            note = (
                "\nGoogle Calendar event was not created because nobody in this meeting "
                "has registered a Google Calendar email."
            )
        else:
            try:
                event = await asyncio.to_thread(
                    create_event,
                    start=start,
                    end=end,
                    summary=topic,
                    description=description,
                    attendee_emails=[record.gmail for record in gmails.values()],
                )
                link = f" {event.html_link}" if event.html_link else ""
                note = (
                    f"\nGoogle Calendar event created and invited: "
                    f"{', '.join(event.invited)}.{link}"
                )
                if missing:
                    note += f"\nNo registered Google Calendar email for: {', '.join(missing)}."
            except CalendarConfigError as e:
                note = f"\nGoogle Calendar event was not created: {e}"
            except Exception as e:  # noqa: BLE001 — calendar failure should not block the .ics
                note = f"\nGoogle Calendar invite failed: {e}"

    return CalendarDelivery(note=note, ics=ics, filename=filename_for(topic))
