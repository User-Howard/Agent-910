import shutil

import discord
from discord import app_commands

from app.agent import respond
from app.history import fetch_conversation
from app.recording import RecordingError, start_recording, stop_recording
from app.settings import settings

intents = discord.Intents.default()
intents.message_content = True


def create_client() -> discord.Client:
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    @client.event
    async def on_ready():
        # Guild-scoped sync so /record and /stop show up immediately in every
        # server the bot is already in, instead of waiting on global propagation.
        for guild in client.guilds:
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
        print(f'We have logged in as {client.user}')

    @tree.command(name="record", description="Join your voice channel and start recording the meeting.")
    async def record(interaction: discord.Interaction):
        member = interaction.user
        voice_state = member.voice if isinstance(member, discord.Member) else None
        if voice_state is None or voice_state.channel is None:
            await interaction.response.send_message(
                "Join a voice channel first, then run `/record` again.", ephemeral=True
            )
            return

        try:
            await start_recording(voice_state.channel, started_by=member.display_name)
        except RecordingError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        await interaction.response.send_message(
            f"\U0001f534 Recording started in **{voice_state.channel.name}**. "
            "Everyone in the channel is being recorded — run `/stop` when the meeting's done."
        )

    @tree.command(name="stop", description="Stop recording and post the mixed meeting audio.")
    async def stop(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        try:
            mixed_path = await stop_recording(interaction.guild_id)
        except RecordingError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        if mixed_path is None:
            await interaction.followup.send("Recording stopped — nobody's audio was captured.")
            return

        try:
            await interaction.followup.send(
                "\U0001f6d1 Recording stopped. Here's the meeting audio:",
                file=discord.File(mixed_path, filename="meeting.mp3"),
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"Recording stopped, but the mixed file couldn't be uploaded ({e})."
            )
        finally:
            shutil.rmtree(mixed_path.parent, ignore_errors=True)

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
                attachments=message.attachments,
            )

        await message.reply(reply)

    return client


def run() -> None:
    client = create_client()
    client.run(settings.discord_token)
