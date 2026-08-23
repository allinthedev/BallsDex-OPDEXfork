from typing import TYPE_CHECKING

import discord

from ballsdex.core.discord import View
from settings.utils import format_currency

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

    from ..models import AuctionOffer
    from .cog import AuctionHouse


class CancelOfferView(View):
    """Lets a buyer pick one of their own pending bids to cancel (refunding the escrow)."""

    def __init__(
        self, interaction: discord.Interaction["BallsDexBot"], offers: list["AuctionOffer"], cog: "AuctionHouse"
    ):
        super().__init__(timeout=90)
        self.restrict_author(interaction.user.id)
        self.bot = cog.bot
        self.cog = cog

        self.select: discord.ui.Select = discord.ui.Select(
            placeholder="Cancel a bid...",
            options=[
                discord.SelectOption(
                    label=f"Bid #{offer.id} — {format_currency(offer.amount, False, self.bot)}",
                    description=f"Listing #{offer.listing_id}",
                    value=str(offer.id),
                )
                for offer in offers[:25]
            ],
        )
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def _on_select(self, interaction: discord.Interaction["BallsDexBot"]):
        offer_id = int(self.select.values[0])
        for item in self.children:
            item.disabled = True  # type: ignore
        await interaction.response.edit_message(view=self)
        try:
            offer = await self.cog.cancel_offer(offer_id, interaction.user.id)
        except RuntimeError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return
        await interaction.followup.send(
            f"Bid #{offer.id} cancelled, **{format_currency(offer.amount, False, self.bot)}** refunded.",
            ephemeral=True,
        )


class ListingOffersView(View):
    """
    Lets a seller accept or reject the current highest bid on each of their listings.
    Only the amount is ever shown — the bidder's identity stays hidden until accepted.
    """

    # 12 listings * 2 buttons = 24, safely under Discord's 25-component-per-view limit
    MAX_LISTINGS = 12

    def __init__(
        self, interaction: discord.Interaction["BallsDexBot"], top_offers: list["AuctionOffer"], cog: "AuctionHouse"
    ):
        super().__init__(timeout=180)
        self.restrict_author(interaction.user.id)
        self.bot = cog.bot
        self.cog = cog

        for offer in top_offers[: self.MAX_LISTINGS]:
            accept_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=f"Accept #{offer.listing_id} — {format_currency(offer.amount, False, self.bot)}",
            )
            reject_button: discord.ui.Button = discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label=f"Reject #{offer.listing_id}",
            )
            accept_button.callback = self._make_callback(offer.id, accept=True)
            reject_button.callback = self._make_callback(offer.id, accept=False)
            self.add_item(accept_button)
            self.add_item(reject_button)

    def _make_callback(self, offer_id: int, accept: bool):
        async def callback(interaction: discord.Interaction["BallsDexBot"]):
            for item in self.children:
                item.disabled = True  # type: ignore
            await interaction.response.edit_message(view=self)

            if accept:
                try:
                    listing, offer = await self.cog.accept_offer(offer_id, interaction.user.id)
                except RuntimeError as error:
                    await interaction.followup.send(str(error), ephemeral=True)
                    return
                await interaction.followup.send(
                    f"Accepted — **{format_currency(offer.amount, False, self.bot)}** added to your balance. "
                    "Other pending bids on that listing were refunded.",
                    ephemeral=True,
                )
                await self.cog.notify_sale(listing, offer)
            else:
                try:
                    offer = await self.cog.reject_offer(offer_id, interaction.user.id)
                except RuntimeError as error:
                    await interaction.followup.send(str(error), ephemeral=True)
                    return
                await interaction.followup.send(
                    f"Rejected — **{format_currency(offer.amount, False, self.bot)}** refunded to the buyer.",
                    ephemeral=True,
                )

        return callback
