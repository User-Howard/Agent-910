# Agent-910

A Discord bot agent built with [discord.py](https://github.com/Rapptz/discord.py) and [pydantic-ai](https://ai.pydantic.dev/).

## Voice meeting recording

`/record` joins the voice channel you're currently in and records the meeting; `/stop`
leaves and posts back a single mixed-down `meeting.mp3` with everyone's audio combined.

- The bot's invite needs the `applications.commands` scope (for the slash commands) and
  the **Connect** permission on the voice channel.
- Voice receiving is not supported by vanilla discord.py, so this uses the
  [`discord-ext-voice-recv`](https://github.com/imayhaveborkedit/discord-ext-voice-recv)
  extension, which requires **ffmpeg** and **libopus** on the host (already installed in
  the Docker image). For local runs outside Docker, install both yourself (e.g.
  `apt install ffmpeg libopus0` on Debian/Ubuntu).
- Only one recording per server at a time; `/stop` mixes and uploads whatever was
  captured, subject to Discord's normal attachment size limit for the server.

## Meeting scheduling

@-mention the bot and ask it to find a time. Everyone just says when they're free in
chat — no accounts, no forms, no separate site. The bot reads what they said, keeps a
running record of it, and works out the overlap.

```
howard: @bot 我們找時間開會討論期末專案，carol 也要來
alice:  我這週三下午跟週五整天都可以
bob:    我週三 2 點後不行，其他時間都可以
carol:  我還不確定耶，要看打工班表

bot:    Alice、Bob、Howard 的時間能配合，Carol 還要等打工班表確認。
```
```
      08/05 08/07
       Wed   Fri
13:00   ▓▓    ██
14:00   ▒▒    ██
18:00   ··    ▓▓

██ 3/3  ▓▓ 2/3  ▒▒ 1/3
```
> `[08/07 (Fri) 13:00-14:00]` `[08/07 (Fri) 14:00-15:00]` `[None of these]`

Clicking a button settles it and posts an `.ics` — one click to add it to Google
Calendar, Apple Calendar or Outlook. If Google Calendar OAuth is configured and
participants have registered Google Calendar emails, the bot also creates a Google
Calendar event from the logged-in account and sends attendee invites. Google Workspace
addresses, such as company `edu.tw` accounts, work here too.

Participants can manage their invite address with slash commands:

```text
/gmail name@company.edu.tw
/mygmail
/forgetgmail
/test_google_calendar_api
```

### How the work is split

Turning "我週三下午跟週五整天都可以" into timestamps is a language problem, so the model
does it. Everything the model is bad at is done in SQLite (`app/availability.py`):

- **Remembering.** Answers accumulate across messages, so people can reply whenever
  they get round to it instead of all at once.
- **Telling "not yet" from "no".** `tentative` ("還不確定") is a distinct state from
  `unavailable` — it keeps that person listed as outstanding instead of quietly
  dropping them from the count.
- **Intersecting.** The overlap is computed, not estimated, so an answer ending at
  18:00 correctly rules out an 18:00 start for a 60-minute meeting.
- **Forgetting on purpose.** Past times are never offered, and a meeting nobody
  settled goes stale after a week rather than capturing the next request.

Meetings are tracked per channel, so two channels never see each other's answers.

## Setup

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
DISCORD_TOKEN=your_discord_bot_token
LLM__API_KEY=your_llm_api_key
TIMEZONE=Asia/Taipei   # optional; the timezone people are speaking in

# Optional: create real Google Calendar events when a time is confirmed.
# The refresh token must include calendar event access for the logged-in account.
GOOGLE_CALENDAR__CLIENT_ID=your_google_oauth_client_id
GOOGLE_CALENDAR__CLIENT_SECRET=your_google_oauth_client_secret
GOOGLE_CALENDAR__REFRESH_TOKEN=refresh_token_for_the_logged_in_google_account
GOOGLE_CALENDAR__CALENDAR_ID=primary
```

## Run with Docker

Build the image:

```bash
docker build -t agent-910 .
```

Run the container:

```bash
docker run --rm --name MyAgent910 --env-file .env agent-910:latest
```

## Deploy

Run `docker compose up -d` once, then add this cron entry to check
`ghcr.io/user-howard/agent-910:main` every minute:

```cron
* * * * * cd /home/howard/Agent-910 && /usr/bin/docker compose up -d --pull always >/dev/null 2>&1
```

The `agent-data` volume holds `meetings.db`, so everyone's stated availability survives
container recreates.
