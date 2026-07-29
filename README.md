# Agent-910

A Discord bot agent built with [discord.py](https://github.com/Rapptz/discord.py) and [pydantic-ai](https://ai.pydantic.dev/).

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
