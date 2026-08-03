import io
import shutil

import discord
from discord import app_commands

from app.agent import (
    compress_for_transcription,
    respond,
    summarize_meeting,
    summarize_recording,
    transcribe_audio,
)
from app.confirm import ConfirmTimeView
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
            recording = await stop_recording(interaction.guild_id)
        except RecordingError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        if recording is None:
            await interaction.followup.send("Recording stopped — nobody's audio was captured.")
            return

        content = "\U0001f6d1 Recording stopped. Here's the meeting audio:"
        files = [discord.File(recording.mixed_audio, filename="meeting.mp3")]
        try:
            result = await summarize_recording(recording.speakers)
            content = f"\U0001f6d1 Recording stopped.\n\n{result.summary}"
            files.append(discord.File(io.BytesIO(result.transcript.encode()), filename="transcript.txt"))
        except Exception as e:  # noqa: BLE001 — a summarization failure shouldn't block the file upload
            content = f"\U0001f6d1 Recording stopped, but summarizing the audio failed ({e}). Here's the raw audio:"

        # Discord caps message content at 2000 chars; keep the audio file either way.
        if len(content) > 2000:
            content = content[:1997] + "..."

        try:
            await interaction.followup.send(content, files=files)
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"Recording stopped, but the mixed file couldn't be uploaded ({e})."
            )
        finally:
            shutil.rmtree(recording.mixed_audio.parent, ignore_errors=True)

    @client.event
    async def on_message(message: discord.Message):
        if message.author == client.user:
            return

        if client.user not in message.mentions:
            return

        audio_attachments = [a for a in message.attachments if (a.content_type or "").startswith("audio/")]
        if audio_attachments:
            async with message.channel.typing():
                summaries = []
                for attachment in audio_attachments:
                    try:
                        data = await attachment.read()
                        compressed = await compress_for_transcription(data)
                        transcript = await transcribe_audio(compressed, f"{attachment.filename}.mp3")
                        summary = await summarize_meeting(transcript)
                    except Exception as e:  # noqa: BLE001 — report per-file, don't drop the rest
                        summary = f"Couldn't summarize this one ({e})."
                    prefix = f"**{attachment.filename}**\n" if len(audio_attachments) > 1 else ""
                    summaries.append(f"{prefix}{summary}")
                reply = "\n\n".join(summaries)
            await message.reply(reply[:2000])
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
                channel_id=message.channel.id,
            )

        # A plain chat reply is just text. A scheduling reply also carries the
        # availability chart and the times to confirm, which Discord renders far
        # better than prose can — the chart as a code block, the times as buttons.
        extras = "\n".join(
            filter(
                None,
                [
                    reply.chart or "",
                    *(f"**{p.slot.label()}** — {p.reason}" for p in reply.proposals),
                ],
            )
        )
        if extras:
            # Trim the prose rather than the chart, so its code block always closes.
            room = 2000 - len(extras) - 1
            content = f"{reply.text[:room]}\n{extras}" if room > 0 else extras[:2000]
        else:
            content = reply.text[:2000]

        view = ConfirmTimeView(reply.proposals, topic=reply.topic, meeting_id=reply.meeting_id) if reply.proposals else None
        sent = await message.reply(content, view=view)
        if view is not None:
            view.message = sent

    return client


def run() -> None:
    client = create_client()
    client.run(settings.discord_token)
