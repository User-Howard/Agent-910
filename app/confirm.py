"""The "which of these works?" buttons the bot posts under a set of proposed times.

The agent can only produce text, but the last step of scheduling is a group decision —
so the candidate times become real Discord buttons. Whoever clicks one settles it for
everyone, which is both clearer and less error-prone than asking people to type a reply.

Settling also closes the meeting in the record, so the next scheduling request in the
channel starts clean instead of inheriting these answers.
"""

import io

import discord

from app import availability
from app.agent import Proposal
from app.invite import build_ics, filename_for

_CONFIRM_TIMEOUT = 60 * 60 * 24  # a day to decide; after that the buttons go quiet


class ConfirmTimeView(discord.ui.View):
    """One button per proposed time, plus a "none of these" escape hatch."""

    def __init__(self, proposals: list[Proposal], *, topic: str, meeting_id: int | None):
        super().__init__(timeout=_CONFIRM_TIMEOUT)
        self.message: discord.Message | None = None
        for index, proposal in enumerate(proposals):
            self.add_item(
                _ConfirmButton(proposal, topic=topic, meeting_id=meeting_id, primary=index == 0)
            )
        self.add_item(_NoneWorkButton())

    def _freeze(self) -> None:
        """Stop taking clicks — the decision is made (or expired)."""
        for child in self.children:
            child.disabled = True
        self.stop()

    async def on_timeout(self) -> None:
        self._freeze()
        if self.message is not None:
            await self.message.edit(view=self)


class _ConfirmButton(discord.ui.Button):
    def __init__(self, proposal: Proposal, *, topic: str, meeting_id: int | None, primary: bool):
        super().__init__(
            label=proposal.slot.label()[:80],  # Discord caps button labels at 80 chars
            style=discord.ButtonStyle.primary if primary else discord.ButtonStyle.secondary,
        )
        self.proposal = proposal
        self.topic = topic
        self.meeting_id = meeting_id

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ConfirmTimeView = self.view  # type: ignore[assignment]
        view._freeze()
        await interaction.response.edit_message(view=view)

        who = interaction.user.display_name
        if self.meeting_id is not None:
            availability.settle(self.meeting_id, self.proposal.slot.start, who)

        # The .ics needs no credentials and nobody's email address, so this is the one
        # path onto people's calendars that always works.
        ics = build_ics(
            start=self.proposal.slot.start,
            end=self.proposal.slot.end,
            summary=self.topic,
            description=f"Confirmed by {who} via Discord. {self.proposal.reason}".strip(),
            organizer=who,
        )
        await interaction.followup.send(
            f"✅ **{self.topic}** is set for **{self.proposal.slot.label()}** "
            f"(confirmed by {who}).\nAdd it to your calendar with the file below.",
            file=discord.File(io.BytesIO(ics), filename=filename_for(self.topic)),
        )


class _NoneWorkButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="None of these", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ConfirmTimeView = self.view  # type: ignore[assignment]
        view._freeze()
        await interaction.response.edit_message(view=view)
        # Deliberately does not settle the meeting: the record stays open so everyone's
        # answers survive into the next round.
        await interaction.followup.send(
            f"{interaction.user.display_name} says none of these work — @-mention me with "
            "what you'd prefer and I'll look again."
        )
