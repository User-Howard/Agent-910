import discord

from app.agent import respond
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

        # Feed the last N messages as context; the agent reads further back via tools if needed.
        # The triggering message itself is excluded here and passed separately below, so the
        # agent knows exactly who @-mentioned it and what they said (instead of guessing).
        initial = await fetch_conversation(
            message.channel,
            limit=settings.initial_history,
            exclude_id=message.id,
        )

        # The LLM takes a while; show a "typing…" indicator as feedback
        async with message.channel.typing():
            reply = await respond(
                message.channel,
                message.id,
                initial,
                asker=message.author.display_name,
                request=message.clean_content,
            )

        await message.reply(reply)

    return client


def run() -> None:
    client = create_client()
    client.run(settings.discord_token)
