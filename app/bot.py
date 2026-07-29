import discord

from app.agent import suggest_meeting_time
from app.history import fetch_conversation
from app.settings import settings

intents = discord.Intents.default()
intents.message_content = True


def create_client() -> discord.Client:
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f'We have logged in as {client.user}')

    @client.event
    async def on_message(message: discord.Message):
        if message.author == client.user:
            return

        if client.user not in message.mentions:
            return

        # Feed the last N messages as context; the agent reads further back via tools if needed
        initial = await fetch_conversation(
            message.channel,
            limit=settings.initial_history,
            exclude_id=message.id,
        )
        if not initial:
            await message.reply("I can't see any conversation in this channel to work from.")
            return

        # The LLM takes a while; show a "typing…" indicator as feedback
        async with message.channel.typing():
            suggestion = await suggest_meeting_time(
                message.channel, message.id, initial
            )

        await message.reply(suggestion)

    return client


def run() -> None:
    client = create_client()
    client.run(settings.discord_token)
