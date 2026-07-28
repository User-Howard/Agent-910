import discord

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

        await message.reply("Hi")

    return client


def run() -> None:
    client = create_client()
    client.run(settings.discord_token)
