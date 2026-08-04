"""Pydantic-ai agents.

The bot's entry point is a general conversational assistant. It chats when people
just want to chat, and treats scheduling a meeting as *one tool it can call* —
`plan_meeting` — rather than the only thing it ever does. The meeting-planning
logic lives in its own sub-agent that the tool runs.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from pydantic_ai import Agent, DocumentUrl, ImageUrl, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from app import availability
from app.calendar_delivery import CalendarDelivery, prepare_calendar_delivery
from app.history import describe_attachments, fetch_conversation
from app.settings import settings

# The endpoint decides where requests go (official OpenAI or a gateway proxy).
# The model is like "openai:gpt-4.1-nano"; keep only the part after the colon.
# Use the Responses API (pydantic-ai's default) so reasoning models + tools work.
_model_id = settings.llm.model.partition(":")[2]
_model = OpenAIResponsesModel(
    _model_id,
    provider=OpenAIProvider(
        base_url=settings.llm.endpoint,
        api_key=settings.llm.api_key,
    ),
)


@dataclass(frozen=True)
class Proposal:
    """One concrete time the agent is putting to the group for confirmation."""

    slot: availability.Slot
    reason: str


@dataclass
class Deps:
    """Dependencies shared by a single agent run and any sub-agents it calls."""

    channel: discord.abc.Messageable  # lets tools read further back in the conversation
    trigger_message_id: int  # the message that triggered the bot; skip it when reading
    conversation: str  # the recent conversation the bot started with
    channel_id: int = 0  # scopes the meeting being tracked to this channel

    # The message that triggered the bot, kept apart from `conversation` because it's
    # excluded from the history fetch. Sub-agents need it too: someone who writes
    # "@bot 我週五下午可以，幫忙喬一下" is stating their availability *in* the trigger,
    # and dropping it would leave their answer unseen until the next turn.
    asker: str = ""
    request: str = ""

    # Filled in by the meeting tools below. The agent can only reply in text, but
    # Discord can do better than text — so what it *found* is collected here and
    # posted by the bot as a chart plus real confirmation buttons.
    chart: str | None = None
    proposals: list[Proposal] = field(default_factory=list)
    meeting_id: int | None = None
    topic: str = "Meeting"
    calendar_delivery: CalendarDelivery | None = None


# --- Meeting-planning sub-agent -------------------------------------------------
# Only reached when the assistant decides scheduling is actually wanted.
#
# The division of labour matters here. Turning "我週三下午跟週五整天都可以" into concrete
# timestamps is a language problem, and the model is the only thing that can do it — so
# that's all it's asked to do. Remembering the answers, telling "hasn't replied" apart
# from "can't make it", and intersecting everyone's windows are all things a model does
# unreliably and SQL does exactly, so those live in `app.availability` instead.

meeting_agent = Agent(
    _model,
    deps_type=Deps,
    instructions=(
        "You help a group in a Discord channel settle on a meeting time, by reading what "
        "they say in chat and keeping a running record of it.\n"
        "\n"
        "WORKFLOW\n"
        "1. Call `open_meeting` first, always. It gives you the topic, the length, and "
        "everything already on record from earlier messages — including who still hasn't "
        "answered. Never assume the record is empty.\n"
        "2. Call `record_availability` only for people this conversation says something "
        "NEW about. If someone's answer is already on record and they haven't spoken "
        "since, leave them alone — re-recording them from memory is how answers get "
        "quietly lost.\n"
        "   When you do record someone, give their COMPLETE availability, not just the "
        "part they mentioned most recently: the call replaces everything they said "
        "before. Narrowing someone's windows means they withdrew that time, so only do "
        "it if they actually did.\n"
        "3. If the request already gives a fixed meeting date/time and duration, call "
        "`confirm_meeting_time` after `open_meeting`. Do not call `review` or "
        "`propose_times` for an already-confirmed time.\n"
        "4. Otherwise, call `review` to get the recomputed overlap. Do not work the overlap out "
        "yourself; you will get it wrong at the edges.\n"
        "5. If `review` shows times that work for everyone who answered, call "
        "`propose_times` with the best 2-3. The bot turns them into buttons.\n"
        "\n"
        "READING TIMES\n"
        "- Resolve relative dates against today's date, given below. '這週三' is the "
        "Wednesday of the current week; if that day has passed, they mean next week.\n"
        "- Convert vague spans conservatively: '下午' is 13:00-18:00, '晚上' is "
        "18:00-22:00, '早上' is 09:00-12:00, '整天' is 09:00-22:00.\n"
        "- Negative and open-ended answers still carry real information. '我週三 2 點後"
        "不行，其他時間都可以' means free until 14:00 on Wednesday AND free on every other "
        "day being discussed. Give them a window on each of those days — dropping them "
        "makes that person look unavailable when they said the opposite.\n"
        "- The days 'being discussed' are the ones already in the record. `open_meeting` "
        "shows you them; cover those, and don't invent days nobody has raised.\n"
        "\n"
        "STATUS — this distinction is the point of the record, so be strict:\n"
        "- 'stated' only when they gave times you can pin to a clock. Windows required.\n"
        "- 'tentative' for real but non-committal answers ('還不確定', '看情況', '應該可以"
        "吧'). No windows. Their name still shows as outstanding.\n"
        "- 'unavailable' when they're out entirely.\n"
        "Never upgrade a vague answer to 'stated' by guessing what they probably meant.\n"
        "\n"
        "Reply in the same language as the conversation, briefly. If people are still "
        "outstanding, say who — `review` tells you. Don't re-list the proposed times in "
        "prose; the buttons already show them."
    ),
)


@meeting_agent.instructions
def _today(ctx: RunContext[Deps]) -> str:
    """Tell the model what "now" is, so relative dates resolve correctly.

    Injected per run rather than baked into the static prompt: a long-lived process
    would otherwise keep resolving "這週三" against the day it booted.
    """
    now = datetime.now(tz=ZoneInfo(settings.timezone))
    return f"Today is {now:%Y-%m-%d (%A)}, current time {now:%H:%M}, timezone {settings.timezone}."


class FreeWindow(BaseModel):
    """One stretch of time a person said they're free."""

    start: str = Field(description="Start, ISO 8601 local time, e.g. 2026-08-05T13:00:00.")
    end: str = Field(description="End, ISO 8601 local time, e.g. 2026-08-05T18:00:00.")


class Candidate(BaseModel):
    """A time the agent wants the group to confirm."""

    start: str = Field(description="When it starts, ISO 8601, e.g. 2026-08-05T14:00:00.")
    reason: str = Field(description="One short line on why this time is a good pick.")


class ConfirmedTime(BaseModel):
    """A meeting time the user has already decided."""

    start: str = Field(description="When it starts, ISO 8601, e.g. 2026-08-05T14:00:00.")
    duration_minutes: int = Field(description="How long the meeting lasts.")
    confirmed_by: str = Field(description="Who confirmed or requested this time.")


def _to_local(value: str) -> datetime:
    """Read an ISO 8601 time from the model, assuming local time when it omits a zone."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo(settings.timezone))
    return parsed.astimezone(ZoneInfo(settings.timezone))


@meeting_agent.tool
async def read_more_messages(ctx: RunContext[Deps], limit: int) -> str:
    """Read more of this channel's recent messages, newest first.

    Call this only when the current conversation isn't enough to decide.

    Args:
        limit: How many messages to read this time. Read incrementally, e.g. 30 or 50.
    """
    conversation = await fetch_conversation(
        ctx.deps.channel,
        limit=limit,
        exclude_id=ctx.deps.trigger_message_id,
    )
    return conversation or "(No more readable text messages in this channel.)"


@meeting_agent.tool
async def open_meeting(
    ctx: RunContext[Deps],
    topic: str,
    participants: list[str],
    duration_minutes: int | None = None,
) -> str:
    """Start or resume tracking this channel's meeting, and read back what's known.

    Call this before anything else. If the channel already has a meeting in progress
    this resumes it, so earlier answers are not lost.

    Args:
        topic: What the meeting is about, in a few words.
        participants: Everyone expected to attend, by the display name they use in chat.
            Listing someone who already answered is harmless.
        duration_minutes: How long it should be. Omit unless someone said.
    """
    duration = duration_minutes or settings.default_meeting_minutes
    meeting = availability.open_meeting(ctx.deps.channel_id, topic, duration)
    availability.retopic(meeting.id, topic, duration)
    availability.note_participants(meeting.id, participants)

    ctx.deps.meeting_id = meeting.id
    ctx.deps.topic = topic
    return f"Meeting #{meeting.id}: {topic}, {duration} min.\nOn record:\n{availability.describe(meeting.id)}"


@meeting_agent.tool
async def record_availability(
    ctx: RunContext[Deps],
    person: str,
    status: str,
    windows: list[FreeWindow] | None = None,
    note: str = "",
) -> str:
    """Write down when one person said they're free. Replaces their previous answer.

    Args:
        person: Their display name, exactly as it appears in the chat.
        status: One of "stated" (gave real times), "tentative" (non-committal),
            "unavailable" (can't attend at all).
        windows: The times they're free. Required for "stated", omitted otherwise.
        note: Their own words, when the status alone loses something worth keeping.
    """
    if ctx.deps.meeting_id is None:
        return "Call `open_meeting` first."
    if status not in {availability.STATED, availability.TENTATIVE, availability.UNAVAILABLE}:
        return f"'{status}' isn't a status. Use stated, tentative or unavailable."
    if status == availability.STATED and not windows:
        return f"'stated' needs windows. If {person} was vague, record them as tentative."

    try:
        parsed = [
            availability.Window(start=_to_local(w.start), end=_to_local(w.end))
            for w in windows or []
        ]
    except ValueError as e:
        return f"Couldn't read those times ({e}) — use ISO 8601 like 2026-08-05T14:00:00."
    if any(w.end <= w.start for w in parsed):
        return "Each window must end after it starts."

    availability.record(ctx.deps.meeting_id, person, status, parsed, note)
    return f"Recorded {person} as {status}."


@meeting_agent.tool
async def review(ctx: RunContext[Deps]) -> str:
    """Recompute and read back the overlap, plus who's still outstanding.

    This is the authority on what works for whom — it intersects the recorded windows
    exactly, and skips anything in the past. It also builds the chart the bot posts.
    """
    if ctx.deps.meeting_id is None:
        return "Call `open_meeting` first."
    ctx.deps.chart = availability.render_heatmap(ctx.deps.meeting_id)
    return availability.describe(ctx.deps.meeting_id)


@meeting_agent.tool
async def propose_times(ctx: RunContext[Deps], candidates: list[Candidate]) -> str:
    """Put 2-3 candidate times to the group as confirmation buttons.

    Only propose times `review` showed as working for everyone who answered — or, if
    nothing does, the best available, saying so in your reply.

    Args:
        candidates: The times to offer, best first.
    """
    if ctx.deps.meeting_id is None:
        return "Call `open_meeting` first."

    meeting = availability.current_meeting(ctx.deps.channel_id)
    duration = timedelta(minutes=meeting.duration_minutes if meeting else settings.default_meeting_minutes)

    proposals = []
    for candidate in candidates:
        try:
            start = _to_local(candidate.start)
        except ValueError as e:
            return f"Couldn't read '{candidate.start}' ({e}) — use ISO 8601."
        proposals.append(
            Proposal(
                slot=availability.Slot(start=start, end=start + duration, who=[]),
                reason=candidate.reason,
            )
        )

    ctx.deps.proposals = proposals
    return f"Offering {len(proposals)} times for confirmation."


@meeting_agent.tool
async def confirm_meeting_time(ctx: RunContext[Deps], confirmed: ConfirmedTime) -> str:
    """Settle an already-decided meeting time and send Google Calendar invites.

    Use this when the user gives the meeting's exact date/time, duration, and
    participants in the request. Call `open_meeting` first so the participant list
    exists in the meeting record.

    Args:
        confirmed: The fixed meeting start, duration, and confirmer.
    """
    if ctx.deps.meeting_id is None:
        return "Call `open_meeting` first."
    if confirmed.duration_minutes <= 0:
        return "duration_minutes must be positive."

    try:
        start = _to_local(confirmed.start)
    except ValueError as e:
        return f"Couldn't read '{confirmed.start}' ({e}) — use ISO 8601."

    end = start + timedelta(minutes=confirmed.duration_minutes)
    availability.retopic(ctx.deps.meeting_id, ctx.deps.topic, confirmed.duration_minutes)
    availability.settle(ctx.deps.meeting_id, start, confirmed.confirmed_by)
    proposal = Proposal(
        slot=availability.Slot(start=start, end=end, who=[]),
        reason="The requester gave this as the confirmed meeting time.",
    )
    description = (
        f"Confirmed by {confirmed.confirmed_by} via Discord. "
        "The requester gave this as the confirmed meeting time."
    )
    ctx.deps.calendar_delivery = await prepare_calendar_delivery(
        meeting_id=ctx.deps.meeting_id,
        start=proposal.slot.start,
        end=proposal.slot.end,
        topic=ctx.deps.topic,
        description=description,
        organizer=confirmed.confirmed_by,
    )
    return (
        f"Confirmed {ctx.deps.topic} for {proposal.slot.label()}."
        f"{ctx.deps.calendar_delivery.note}"
    )


# --- Top-level conversational assistant ----------------------------------------

assistant_agent = Agent(
    _model,
    deps_type=Deps,
    instructions=(
        "You're a friendly assistant that lives in a Discord channel and replies when "
        "someone @-mentions you. Read the room and decide what they want:\n"
        "- If they're just chatting, asking a question, or being social, chat back "
        "naturally and briefly.\n"
        "- If they want to find a time to meet / schedule something, call `plan_meeting` "
        "and relay its answer.\n"
        "Don't force meeting-scheduling on a casual conversation. When you're unsure "
        "whether they want to schedule, just ask.\n"
        "Reply in the same language as the conversation."
    ),
)


@assistant_agent.tool
async def plan_meeting(ctx: RunContext[Deps]) -> str:
    """Work out good meeting times from the channel conversation.

    Call this when the people in the chat want to schedule or find a time to meet.
    It reads the conversation (and further back if needed), checks availability, and
    returns concrete suggested times. Returns that suggestion as text.
    """
    return await _run_meeting_agent(ctx.deps)


async def _run_meeting_agent(deps: Deps) -> str:
    """Run the scheduling agent directly for meeting/calendar requests."""
    result = await meeting_agent.run(
        f"Here's this channel's recent conversation (latest {settings.initial_history}):"
        f"\n\n{deps.conversation}\n"
        f"{deps.asker}: {deps.request}\n\n"
        "That last line is the message that just triggered you — treat it as part of the "
        "conversation, including any availability it states.\n"
        "If it asks to directly create a Google Calendar event, invite attendees, or "
        "says the meeting time is already confirmed, this is a meeting request. If it "
        "gives a fixed date/time and duration, call `open_meeting`, then "
        "`confirm_meeting_time`. Otherwise help them find a good meeting time; if it's "
        "not enough to decide, use the tools to read further back.",
        deps=deps,
    )
    return result.output


def _looks_like_meeting_request(text: str) -> bool:
    """Cheap routing guard so direct calendar requests don't get answered as chat."""
    lowered = text.casefold()
    strong = [
        "google calendar",
        "calendar 活動",
        "行事曆",
        "邀請",
        "建立活動",
        "直接建立",
        "會議已確定",
        "已確定",
    ]
    meeting = ["meeting", "會議", "開會", "辦一個meeting", "schedule", "安排"]
    timeish = ["時間", "持續", "分鐘", "am", "pm", "台北時間", "202"]
    return any(token in lowered for token in strong) or (
        any(token in lowered for token in meeting) and any(token in lowered for token in timeish)
    )


@dataclass
class Reply:
    """What the bot should post: the assistant's text, plus anything Discord can render."""

    text: str
    chart: str | None = None
    proposals: list[Proposal] = field(default_factory=list)
    topic: str = "Meeting"
    meeting_id: int | None = None
    calendar_delivery: CalendarDelivery | None = None


async def respond(
    channel: discord.abc.Messageable,
    trigger_message_id: int,
    initial_conversation: str,
    asker: str,
    request: str,
    attachments: list[discord.Attachment] | None = None,
    channel_id: int = 0,
) -> Reply:
    """Hand the recent conversation to the assistant and return what to post.

    The assistant chats directly, or calls `plan_meeting` when scheduling is wanted.

    Args:
        asker: Display name of the person who @-mentioned the bot.
        request: The exact message they sent (mentions rendered as readable names).
        attachments: Files on the triggering message. Images and PDFs are sent
            to the model directly; other file types are only mentioned by
            name, since the model can't view them.
        channel_id: Scopes the tracked meeting to this channel.
    """
    deps = Deps(
        channel=channel,
        trigger_message_id=trigger_message_id,
        conversation=initial_conversation,
        channel_id=channel_id,
        asker=asker,
        request=request,
    )
    history = initial_conversation or "(no earlier messages in this channel)"

    images: list[discord.Attachment] = []
    documents: list[discord.Attachment] = []
    other: list[discord.Attachment] = []
    for attachment in attachments or []:
        content_type = attachment.content_type or ""
        if content_type.startswith("image/"):
            images.append(attachment)
        elif content_type == "application/pdf":
            documents.append(attachment)
        else:
            other.append(attachment)

    text = (
        f"Here's this channel's recent conversation (latest {settings.initial_history}):"
        f"\n\n{history}\n\n"
        f'{asker} just @-mentioned you and said: "{request}"'
    )
    if other:
        text += f"\n{asker} also attached {describe_attachments(other)}, which you can't view directly."
    text += "\nReply to them appropriately."

    files = [ImageUrl(url=a.url) for a in images] + [DocumentUrl(url=a.url) for a in documents]
    if not files and _looks_like_meeting_request(request):
        output = await _run_meeting_agent(deps)
    else:
        user_prompt = [text, *files] if files else text
        result = await assistant_agent.run(user_prompt, deps=deps)
        output = result.output
    return Reply(
        text=output,
        chart=deps.chart,
        proposals=deps.proposals,
        topic=deps.topic,
        meeting_id=deps.meeting_id,
        calendar_delivery=deps.calendar_delivery,
    )


# --- Meeting recording: transcription & summary ---------------------------------

_transcription_client = AsyncOpenAI(base_url=settings.llm.endpoint, api_key=settings.llm.api_key)

summary_agent = Agent(
    _model,
    instructions=(
        "You summarize a meeting transcript. Give a short summary, then the key "
        "discussion points, decisions made, and action items (who/what, if mentioned). "
        "Be concise. Reply in the same language as the transcript."
    ),
)


def _format_timestamp(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


async def transcribe_audio(data: bytes, filename: str) -> str:
    """Transcribe raw audio bytes (e.g. an uploaded mp3) to text.

    Each line is prefixed with a [MM:SS] timestamp of when it was said,
    relative to the start of the audio file.
    """
    transcript = await _transcription_client.audio.transcriptions.create(
        model=settings.llm.transcription_model,
        file=(filename, data),
        response_format="verbose_json",
        timestamp_granularities=["segment"],
    )
    if not transcript.segments:
        return transcript.text
    return "\n".join(f"[{_format_timestamp(seg.start)}] {seg.text.strip()}" for seg in transcript.segments)


async def compress_for_transcription(data: bytes) -> bytes:
    """Downmix arbitrary audio bytes to mono 16kHz mp3 before sending to Whisper.

    Raw/lightly-compressed audio (e.g. the recorder's 48kHz stereo per-speaker
    WAVs, or whatever format a user uploads) can easily blow past OpenAI's
    25MB transcription upload limit. Speech transcription doesn't need stereo
    or 48kHz, so compressing first avoids that limit for anything but
    extremely long audio. ffmpeg auto-detects the input format/codec from the
    byte stream itself, so this works regardless of the source format.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "32k",
        "-f",
        "mp3",
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, stderr = await proc.communicate(input=data)
    if proc.returncode != 0:
        raise RuntimeError(f"Compressing audio for transcription failed: {stderr.decode(errors='replace')[-500:]}")
    return out


async def _transcribe_speaker(name: str, audio_path: Path) -> str:
    data = await asyncio.to_thread(audio_path.read_bytes)
    compressed = await compress_for_transcription(data)
    text = await transcribe_audio(compressed, f"{audio_path.stem}.mp3")
    return f"{name}:\n{text}"


@dataclass
class MeetingSummary:
    transcript: str
    """Full speaker-labeled transcript, e.g. "Alice:\\n...\\n\\nBob:\\n..."."""

    summary: str
    """The LLM's summary of the transcript."""


async def summarize_recording(speakers: list[tuple[str, Path]]) -> MeetingSummary:
    """Summarize a meeting from each speaker's individual (pre-mix) audio file.

    Transcribing each speaker separately, rather than the mixed-down track,
    means the transcript comes with real speaker attribution — Whisper has no
    diarization, so a single mixed track would just be "what was said" with no
    reliable "who said it".
    """
    labeled_transcripts = await asyncio.gather(
        *[_transcribe_speaker(name, path) for name, path in speakers]
    )
    transcript = "\n\n".join(labeled_transcripts)
    summary = await summarize_meeting(transcript)
    return MeetingSummary(transcript=transcript, summary=summary)


async def summarize_meeting(transcript: str) -> str:
    """Summarize a meeting transcript: key points, decisions, action items."""
    result = await summary_agent.run(transcript)
    return result.output
