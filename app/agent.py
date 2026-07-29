"""A pydantic-ai agent that helps a team pick a meeting time."""

from dataclasses import dataclass

import discord
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.history import fetch_conversation
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


@dataclass
class MeetingDeps:
    """Dependencies needed for a single agent run."""

    channel: discord.abc.Messageable  # lets tools read further back in the conversation
    trigger_message_id: int  # the message that triggered the bot; skip it when reading


meeting_agent = Agent(
    _model,
    deps_type=MeetingDeps,
    instructions=(
        "You help a team schedule a meeting from their chat. Figure out the topic, "
        "who's involved, and any time preferences.\n"
        "You start with the last 10 messages. If that's not enough, call "
        "`read_more_messages` to read a bit further back — just enough, not too much.\n"
        "Once you have a time range, call `find_free_slots` for everyone's common "
        "availability, then suggest 2-3 concrete times with a short reason each. "
        "Reply in the same language as the conversation. If info is missing, say what's "
        "missing instead of guessing."
    ),
)


@meeting_agent.tool
async def read_more_messages(ctx: RunContext[MeetingDeps], limit: int) -> str:
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
async def find_free_slots(
    ctx: RunContext[MeetingDeps],
    earliest: str,
    latest: str,
    duration_minutes: int,
) -> str:
    """Find everyone's common free slots within a time range.

    Args:
        earliest: Earliest possible meeting time (ISO 8601, e.g. 2026-07-29T09:00:00).
        latest: Latest the meeting should end (ISO 8601).
        duration_minutes: Meeting length in minutes.
    """
    # TODO: hook up Google Calendar and return real availability.
    # Placeholder for now so the whole agent flow can run end to end.
    return (
        f"(Google Calendar not connected yet, fake data) Common free slots between "
        f"{earliest} and {latest} for {duration_minutes} minutes: "
        f"7/29 14:00–15:00, 7/30 10:00–11:00."
    )


async def suggest_meeting_time(
    channel: discord.abc.Messageable,
    trigger_message_id: int,
    initial_conversation: str,
) -> str:
    """Hand the recent conversation to the agent and return suggested meeting times."""
    deps = MeetingDeps(channel=channel, trigger_message_id=trigger_message_id)
    result = await meeting_agent.run(
        f"Here's this channel's recent conversation (latest {settings.initial_history}):"
        f"\n\n{initial_conversation}\n\n"
        "Help us find a good meeting time; if it's not enough to decide, use the tools "
        "to read further back.",
        deps=deps,
    )
    return result.output
