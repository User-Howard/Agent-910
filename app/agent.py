"""Pydantic-ai agents.

The bot's entry point is a general conversational assistant. It chats when people
just want to chat, and treats scheduling a meeting as *one tool it can call* —
`plan_meeting` — rather than the only thing it ever does. The meeting-planning
logic lives in its own sub-agent that the tool runs.
"""

from dataclasses import dataclass

import discord
from pydantic_ai import Agent, DocumentUrl, ImageUrl, RunContext
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

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


@dataclass
class Deps:
    """Dependencies shared by a single agent run and any sub-agents it calls."""

    channel: discord.abc.Messageable  # lets tools read further back in the conversation
    trigger_message_id: int  # the message that triggered the bot; skip it when reading
    conversation: str  # the recent conversation the bot started with


# --- Meeting-planning sub-agent -------------------------------------------------
# Only reached when the assistant decides scheduling is actually wanted.

meeting_agent = Agent(
    _model,
    deps_type=Deps,
    instructions=(
        "You help a team schedule a meeting from their chat. Figure out the topic, "
        "who's involved, and any time preferences.\n"
        "You start with the recent conversation you're given. If that's not enough, call "
        "`read_more_messages` to read a bit further back — just enough, not too much.\n"
        "Once you have a time range, call `find_free_slots` for everyone's common "
        "availability, then suggest 2-3 concrete times with a short reason each. "
        "Reply in the same language as the conversation. If info is missing, say what's "
        "missing instead of guessing."
    ),
)


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
async def find_free_slots(
    ctx: RunContext[Deps],
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
    result = await meeting_agent.run(
        f"Here's this channel's recent conversation (latest {settings.initial_history}):"
        f"\n\n{ctx.deps.conversation}\n\n"
        "Help them find a good meeting time; if it's not enough to decide, use the "
        "tools to read further back.",
        deps=ctx.deps,
    )
    return result.output


async def respond(
    channel: discord.abc.Messageable,
    trigger_message_id: int,
    initial_conversation: str,
    asker: str,
    request: str,
    attachments: list[discord.Attachment] | None = None,
) -> str:
    """Hand the recent conversation to the assistant and return its reply.

    The assistant chats directly, or calls `plan_meeting` when scheduling is wanted.

    Args:
        asker: Display name of the person who @-mentioned the bot.
        request: The exact message they sent (mentions rendered as readable names).
        attachments: Files on the triggering message. Images and PDFs are sent
            to the model directly; other file types are only mentioned by
            name, since the model can't view them.
    """
    deps = Deps(
        channel=channel,
        trigger_message_id=trigger_message_id,
        conversation=initial_conversation,
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
    user_prompt = [text, *files] if files else text
    result = await assistant_agent.run(user_prompt, deps=deps)
    return result.output
