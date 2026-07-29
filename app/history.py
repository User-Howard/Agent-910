"""Read and format conversation context from a Discord channel."""

import discord


async def fetch_conversation(
    channel: discord.abc.Messageable,
    *,
    limit: int,
    exclude_id: int | None = None,
) -> str:
    """Fetch the channel's latest `limit` text messages as "name: content" lines.

    Args:
        channel: The channel to read.
        limit: Max messages to read, newest first.
        exclude_id: A message id to skip (usually the @-mention that triggered the bot).

    Returns:
        The conversation oldest-to-newest, or an empty string if nothing usable.
    """
    lines: list[str] = []
    async for msg in channel.history(limit=limit):
        if exclude_id is not None and msg.id == exclude_id:
            continue
        if not msg.content:
            continue
        lines.append(f"{msg.author.display_name}: {msg.content}")

    lines.reverse()
    return "\n".join(lines)
