"""Create Google Calendar events from confirmed Discord meeting times."""

import json
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.settings import settings

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3/calendars"
_TIMEOUT_SECONDS = 15


class CalendarConfigError(RuntimeError):
    """Google Calendar is not configured for this bot."""


class CalendarApiError(RuntimeError):
    """Google Calendar rejected or failed the request."""


@dataclass(frozen=True)
class CalendarEvent:
    html_link: str
    invited: list[str]


@dataclass(frozen=True)
class CalendarHealth:
    calendar_id: str
    summary: str
    timezone: str


def is_configured() -> bool:
    """Whether the bot has enough OAuth settings to call Google Calendar."""
    return settings.google_calendar.enabled


def _post_form(url: str, data: dict[str, str]) -> dict:
    body = urlencode(data).encode()
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _send(request)


def _send(request: Request) -> dict:
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise CalendarApiError(f"Google Calendar API returned {e.code}: {detail}") from e
    except URLError as e:
        raise CalendarApiError(f"Could not reach Google Calendar API: {e.reason}") from e


def _access_token() -> str:
    calendar = settings.google_calendar
    if not calendar.enabled:
        raise CalendarConfigError(
            "Google Calendar is not configured. Set GOOGLE_CALENDAR__CLIENT_ID, "
            "GOOGLE_CALENDAR__CLIENT_SECRET and GOOGLE_CALENDAR__REFRESH_TOKEN."
        )

    payload = _post_form(
        _TOKEN_URL,
        {
            "client_id": calendar.client_id,
            "client_secret": calendar.client_secret,
            "refresh_token": calendar.refresh_token,
            "grant_type": "refresh_token",
        },
    )
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise CalendarApiError("Google OAuth token refresh did not return an access token.")
    return token


def create_event(
    *,
    start: datetime,
    end: datetime,
    summary: str,
    description: str,
    attendee_emails: list[str],
) -> CalendarEvent:
    """Create a Google Calendar event and invite the given email addresses."""
    invited = sorted(set(attendee_emails))
    if not invited:
        raise CalendarConfigError("No registered Google Calendar emails were found for this meeting.")

    token = _access_token()
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "attendees": [{"email": email} for email in invited],
    }
    calendar_id = quote(settings.google_calendar.calendar_id, safe="")
    url = f"{_CALENDAR_API}/{calendar_id}/events?sendUpdates=all"
    request = Request(
        url,
        data=json.dumps(event).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    payload = _send(request)
    link = payload.get("htmlLink")
    return CalendarEvent(html_link=link if isinstance(link, str) else "", invited=invited)


def test_calendar_api() -> CalendarHealth:
    """Refresh OAuth and read the configured calendar metadata."""
    token = _access_token()
    calendar_id = quote(settings.google_calendar.calendar_id, safe="")
    url = f"{_CALENDAR_API}/{calendar_id}"
    request = Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    payload = _send(request)
    summary = payload.get("summary")
    timezone = payload.get("timeZone")
    return CalendarHealth(
        calendar_id=settings.google_calendar.calendar_id,
        summary=summary if isinstance(summary, str) and summary else "(unnamed calendar)",
        timezone=timezone if isinstance(timezone, str) and timezone else "(unknown timezone)",
    )
