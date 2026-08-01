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

## Setup

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
DISCORD_TOKEN=your_discord_bot_token
LLM__API_KEY=your_llm_api_key
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
* * * * * cd /home/howard/Documents/Agent-910 && /usr/bin/docker compose up -d --pull always >/dev/null 2>&1
```
