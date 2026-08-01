"""Read and format conversation context from a Discord channel."""

import discord


def describe_attachments(attachments: list[discord.Attachment]) -> str:
    """Render attachments as a "[attached: a.png, b.pdf]" style text note.

    Used for messages further back in history, where we pass plain text
    context rather than re-fetching and re-sending each image to the model.
    """
    if not attachments:
        return ""
    names = ", ".join(a.filename for a in attachments)
    return f"[attached: {names}]"


async def fetch_conversation(
    channel: discord.abc.Messageable,
    *,
    limit: int,
    exclude_id: int | None = None,
) -> str:
    """Fetch the channel's latest `limit` messages as "name: content" lines.

    Attachments are noted by filename (e.g. "[attached: photo.png]") rather
    than sent as image content, since this is background context rather than
    the message that's actually being responded to.

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
        text = " ".join(filter(None, [msg.content, describe_attachments(msg.attachments)]))
        if not text:
            continue
        lines.append(f"{msg.author.display_name}: {text}")

    lines.reverse()
    return "\n".join(lines)
