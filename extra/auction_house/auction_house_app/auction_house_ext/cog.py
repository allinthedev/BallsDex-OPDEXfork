import logging
import random
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from auction_house_app import pricing
from auction_house_app.models import (
    AuctionBoosterRole,
    AuctionGuildConfig,
    AuctionListing,
    AuctionOffer,
    AuctionSettings,
    DirectSaleLog,
    GiveawayLog,
    HotelStock,
    ServerActivity,
    SpecialPriceModifier,
    StatBonusModifier,
    get_hotel_player_sync,
)
from discord import app_commands
from discord.ext import commands, tasks
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.menus.old import FieldPageSource, Pages
from ballsdex.core.utils.transformers import BallInstanceTransform
from ballsdex.core.utils.utils import can_mention
from bd_models.models import BallInstance, Player
from settings.models import settings
from settings.utils import format_currency

from . import views

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)

# vivid blue used across every Buggy's Auction House embed
AUCTION_COLOR = discord.Colour.from_rgb(0, 132, 255)

SORT_CHOICES = [
    app_commands.Choice(name="Rarity", value="rarity"),
    app_commands.Choice(name="Most recent", value="recent"),
    app_commands.Choice(name="Price", value="price"),
]
_LISTING_SORT_FIELDS = {"rarity": "instance__ball__rarity", "recent": "-created_at", "price": "asking_price"}
_STOCK_SORT_FIELDS = {"rarity": "instance__ball__rarity", "recent": "-acquired_at", "price": "resale_price"}


class AuctionHouse(commands.GroupCog, name="Buggy's Auction House", group_name="auction"):
    """
    Sell treasures to Buggy's Auction House, or list them for player bids.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    async def cog_load(self):
        self.sweep_listings.start()
        self.giveaway_draw.start()

    def cog_unload(self):
        self.sweep_listings.cancel()
        self.giveaway_draw.cancel()

    # -- shared helpers -----------------------------------------------------------------

    async def _load_pricing_context(self) -> tuple[AuctionSettings, dict[int, int], dict[int, int]]:
        auction_settings = await AuctionSettings.aload()
        special_modifiers = {sm.special_id: sm.percent async for sm in SpecialPriceModifier.objects.all()}
        stat_modifiers = {sm.value: sm.percent async for sm in StatBonusModifier.objects.all()}
        return auction_settings, special_modifiers, stat_modifiers

    async def _get_guild_config(self, server_id: int) -> AuctionGuildConfig | None:
        return await AuctionGuildConfig.objects.filter(server_id=server_id).afirst()

    async def _get_booster_role(
        self, user: discord.User | discord.Member, server_id: int, field: str
    ) -> AuctionBoosterRole | None:
        """
        Best applicable booster role for `user` in `server_id`, ranked by `field`
        (`"buy_discount_percent"` or `"sell_bonus_percent"`) — highest wins if several apply.
        """
        if not isinstance(user, discord.Member):
            return None
        role_ids = [role.id for role in user.roles]
        if not role_ids:
            return None
        best: AuctionBoosterRole | None = None
        async for booster in AuctionBoosterRole.objects.filter(server_id=server_id, role_id__in=role_ids):
            if best is None or getattr(booster, field) > getattr(best, field):
                best = booster
        return best

    async def notify_sale(self, listing: AuctionListing, offer: AuctionOffer):
        """Tag the buyer in the server's configured notification channel, if any."""
        guild_config = await self._get_guild_config(listing.server_id)
        if guild_config is None or guild_config.notification_channel_id is None:
            return
        channel = self.bot.get_channel(guild_config.notification_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(guild_config.notification_channel_id)
            except discord.HTTPException:
                return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            await channel.send(
                f"\N{PARTY POPPER} <@{offer.buyer.discord_id}> your offer of "
                f"**{format_currency(offer.amount, False, self.bot)}** was accepted for "
                f"{listing.instance.description(include_emoji=True, bot=self.bot)}!",
                allowed_mentions=await can_mention([offer.buyer]),
            )
        except discord.HTTPException:
            log.warning("Failed to send auction sale notification in channel %s", channel.id)

    # -- /auction setchannel ------------------------------------------------------------------------

    @app_commands.command(name="setchannel")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.checks.bot_has_permissions(send_messages=True, embed_links=True)
    @app_commands.guild_only()
    async def set_channel(
        self, interaction: discord.Interaction["BallsDexBot"], channel: discord.TextChannel | None = None
    ):
        """
        Set the channel where Buggy's Auction House posts sale notifications.

        Parameters
        ----------
        channel: discord.TextChannel
            The channel to use, current one if not specified.
        """
        if channel is None:
            if isinstance(interaction.channel, discord.TextChannel):
                channel = interaction.channel
            else:
                await interaction.response.send_message(
                    "The current channel is not a valid text channel.", ephemeral=True
                )
                return
        server_id = interaction.guild_id
        assert server_id is not None
        await AuctionGuildConfig.objects.aupdate_or_create(
            server_id=server_id, defaults={"notification_channel_id": channel.id}
        )
        await interaction.response.send_message(
            f"Sale notifications will now be posted in {channel.mention}.", ephemeral=True
        )

    # -- /auction sell ------------------------------------------------------------------------

    @app_commands.command(name="sell")
    async def sell(self, interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
        """
        Sell a treasure directly to Buggy's Auction House for an instant payout.

        Parameters
        ----------
        countryball: BallInstance
            The treasure you want to sell.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not countryball.is_tradeable or countryball.deleted:
            await interaction.followup.send(f"This {settings.collectible_name} can't be sold.")
            return
        if countryball.special_id is not None:
            await interaction.followup.send(
                "Special treasures can't be sold directly to Buggy — list them for auction instead with "
                "`/auction create`."
            )
            return

        auction_settings, _, stat_modifiers = await self._load_pricing_context()
        if countryball.countryball.rarity == auction_settings.excluded_rarity:
            await interaction.followup.send("This treasure's rarity can't be sold to Buggy.")
            return
        if await self._is_already_committed(countryball):
            await interaction.followup.send("This treasure is already listed or already belongs to Buggy.")
            return

        server_id = interaction.guild_id
        assert server_id is not None
        today = timezone.localdate()
        sale_log, _ = await DirectSaleLog.objects.aget_or_create(
            player_id=countryball.player_id, server_id=server_id, sale_date=today
        )
        if sale_log.count >= auction_settings.direct_sale_daily_limit:
            await interaction.followup.send(
                f"You've reached the daily limit of {auction_settings.direct_sale_daily_limit} direct sales "
                "to Buggy. Try again tomorrow."
            )
            return

        booster = await self._get_booster_role(interaction.user, server_id, "sell_bonus_percent")
        bonus_percent = booster.sell_bonus_percent if booster else 0
        price = pricing.direct_sale_price(countryball, auction_settings, stat_modifiers, bonus_percent)

        embed = discord.Embed(
            title="Sell to Buggy's Auction House",
            description=(
                f"{countryball.description(include_emoji=True, bot=self.bot)}\n\n"
                f"Buggy offers you **{format_currency(price, False, self.bot)}** for this "
                f"{settings.collectible_name}{' (booster bonus included)' if bonus_percent else ''}.\n\n"
                "This is final — the treasure leaves your inventory immediately."
            ),
            color=AUCTION_COLOR,
        )
        view = ConfirmChoiceView(interaction, accept_message="Sold!", cancel_message="Sale cancelled.")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            return

        resale_price = max(price, round(price * (1 + auction_settings.resale_markup_percent / 100)))
        await sync_to_async(self._settle_direct_sale)(countryball.pk, price, resale_price, server_id)
        await interaction.followup.send(f"Sold for **{format_currency(price, False, self.bot)}**!", ephemeral=True)

    def _settle_direct_sale(self, instance_id: int, price: int, resale_price: int, server_id: int):
        with transaction.atomic():
            instance = BallInstance.objects.select_related("player").select_for_update().get(pk=instance_id)
            player = instance.player
            player.money = F("money") + price
            player.save(update_fields=["money"])

            hotel = get_hotel_player_sync()
            instance.player = hotel
            instance.favorite = False
            instance.save(update_fields=["player", "favorite"])

            HotelStock.objects.create(
                instance=instance, server_id=server_id, buyout_price=price, resale_price=resale_price
            )
            today = timezone.localdate()
            DirectSaleLog.objects.filter(
                player_id=player.pk, server_id=server_id, sale_date=today
            ).update(count=F("count") + 1)

    # -- /auction create ------------------------------------------------------------------------

    @app_commands.command(name="create")
    @app_commands.describe(price="Your asking price", hours="How long the listing stays up, in hours")
    async def create_listing(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        countryball: BallInstanceTransform,
        price: app_commands.Range[int, 1],
        hours: app_commands.Range[int, 1, 72],
    ):
        """
        List a treasure on Buggy's Auction House. Buyers bid, you choose to accept or reject the highest.

        Parameters
        ----------
        countryball: BallInstance
            The treasure you want to list.
        price: int
            Your asking price (shown to buyers as a reference).
        hours: int
            How long the listing stays up, between 1 and 72 hours.
        """
        if not countryball:
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not countryball.is_tradeable or countryball.deleted:
            await interaction.followup.send(f"This {settings.collectible_name} can't be listed.")
            return

        auction_settings, special_modifiers, stat_modifiers = await self._load_pricing_context()
        if countryball.countryball.rarity == auction_settings.excluded_rarity:
            await interaction.followup.send("This treasure's rarity can't be listed for auction.")
            return
        if not (auction_settings.min_listing_hours <= hours <= auction_settings.max_listing_hours):
            await interaction.followup.send(
                f"Duration must be between {auction_settings.min_listing_hours}h and "
                f"{auction_settings.max_listing_hours}h."
            )
            return
        if await countryball.is_locked():
            await interaction.followup.send(f"This {settings.collectible_name} is currently locked.")
            return
        if await self._is_already_committed(countryball):
            await interaction.followup.send("This treasure is already listed or already belongs to Buggy.")
            return

        active_count = await AuctionListing.objects.filter(
            seller=countryball.player, status=AuctionListing.Status.ACTIVE
        ).acount()
        if active_count >= auction_settings.max_active_listings:
            await interaction.followup.send(
                f"You can only have {auction_settings.max_active_listings} active listings at once."
            )
            return

        recommended = pricing.recommended_price(countryball, auction_settings, special_modifiers, stat_modifiers)
        server_id = interaction.guild_id
        assert server_id is not None

        embed = discord.Embed(
            title="Create a listing on Buggy's Auction House",
            description=(
                f"{countryball.description(include_emoji=True, bot=self.bot)}\n\n"
                f"**Recommended price:** {format_currency(recommended, False, self.bot)}\n"
                f"**Your asking price:** {format_currency(price, False, self.bot)}\n"
                f"**Duration:** {hours}h\n\n"
                "Buyers will bid on this listing. You'll only see the highest bid, and can accept or reject "
                "it with `/auction mylistings` — you won't know who placed it unless you accept."
            ),
            color=AUCTION_COLOR,
        )
        view = ConfirmChoiceView(interaction, accept_message="Listed!", cancel_message="Listing cancelled.")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            return

        await sync_to_async(self._create_listing)(countryball.pk, price, hours, server_id)
        await interaction.followup.send("Your treasure has been listed on Buggy's Auction House!", ephemeral=True)

    def _create_listing(self, instance_id: int, price: int, hours: int, server_id: int):
        with transaction.atomic():
            instance = BallInstance.objects.select_related("player").select_for_update().get(pk=instance_id)
            instance.locked = timezone.now()
            instance.save(update_fields=["locked"])
            AuctionListing.objects.create(
                instance=instance,
                seller=instance.player,
                server_id=server_id,
                asking_price=price,
                duration_hours=hours,
                expires_at=timezone.now() + timedelta(hours=hours),
            )

    async def _is_already_committed(self, instance: BallInstance) -> bool:
        listed = await AuctionListing.objects.filter(
            instance=instance, status=AuctionListing.Status.ACTIVE
        ).aexists()
        if listed:
            return True
        return await HotelStock.objects.filter(instance=instance).aexists()

    # -- /auction browse ------------------------------------------------------------------------

    @app_commands.command(name="browse")
    @app_commands.describe(name="Only show listings whose treasure name contains this", sort="How to order the results")
    @app_commands.choices(sort=SORT_CHOICES)
    async def browse(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        name: str | None = None,
        sort: app_commands.Choice[str] | None = None,
    ):
        """
        Browse treasures currently listed on Buggy's Auction House on this server.

        Parameters
        ----------
        name: str
            Only show listings whose treasure name contains this.
        sort: str
            How to order the results.
        """
        await interaction.response.defer(thinking=True)
        server_id = interaction.guild_id
        qs = AuctionListing.objects.filter(
            server_id=server_id, status=AuctionListing.Status.ACTIVE
        ).select_related("instance", "instance__ball", "instance__special")
        if name:
            qs = qs.filter(instance__ball__country__icontains=name)
        order = _LISTING_SORT_FIELDS.get(sort.value if sort else "", "expires_at")
        listings = [listing async for listing in qs.order_by(order)]
        if not listings:
            await interaction.followup.send(
                "No listings match that name." if name else "No treasures are currently listed on this server's auction house."
            )
            return

        entries = [
            (
                f"#{listing.id} — {listing.instance.description(include_emoji=True, bot=self.bot)}",
                f"Asking: {format_currency(listing.asking_price, False, self.bot)} • "
                f"Expires {discord.utils.format_dt(listing.expires_at, 'R')}",
            )
            for listing in listings
        ]
        source = FieldPageSource(entries, per_page=8, inline=False)
        source.embed.title = "Buggy's Auction House — Active listings"
        source.embed.colour = AUCTION_COLOR
        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    # -- /auction bid ------------------------------------------------------------------------

    @app_commands.command(name="bid")
    @app_commands.rename(listing_id="listing")
    async def bid(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        listing_id: int,
        amount: app_commands.Range[int, 1],
    ):
        """
        Bid on a treasure listed on Buggy's Auction House. Your coins are held until the seller decides.

        Parameters
        ----------
        listing_id: int
            The listing you want to bid on.
        amount: int
            How much you're bidding.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            listing = await AuctionListing.objects.select_related("instance", "seller").aget(
                pk=listing_id, server_id=interaction.guild_id
            )
        except AuctionListing.DoesNotExist:
            await interaction.followup.send("This listing doesn't exist on this server.")
            return
        if listing.status != AuctionListing.Status.ACTIVE:
            await interaction.followup.send("This listing is no longer active.")
            return

        buyer, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        if listing.seller_id == buyer.pk:
            await interaction.followup.send("You can't bid on your own listing.")
            return
        if not buyer.can_afford(amount):
            await interaction.followup.send(
                f"You don't have enough {settings.currency_display_plural(self.bot)} for that bid.\n"
                f"Your balance: **{format_currency(buyer.money, False, self.bot)}** • "
                f"Bid amount: **{format_currency(amount, False, self.bot)}**"
            )
            return
        already_offered = await AuctionOffer.objects.filter(
            listing=listing, buyer=buyer, status=AuctionOffer.Status.PENDING
        ).aexists()
        if already_offered:
            await interaction.followup.send(
                "You already have a pending bid on this listing. Cancel it first with `/auction mybids` if you "
                "want to change your amount."
            )
            return

        try:
            await sync_to_async(self._create_offer)(listing.pk, buyer.pk, amount)
        except RuntimeError as error:
            await interaction.followup.send(str(error))
            return
        await interaction.followup.send(
            f"Bid of **{format_currency(amount, False, self.bot)}** submitted!", ephemeral=True
        )

    def _create_offer(self, listing_id: int, buyer_id: int, amount: int):
        with transaction.atomic():
            listing = AuctionListing.objects.select_for_update().get(pk=listing_id)
            if listing.status != AuctionListing.Status.ACTIVE:
                raise RuntimeError("This listing is no longer active.")
            buyer = Player.objects.select_for_update().get(pk=buyer_id)
            if buyer.money < amount:
                raise RuntimeError(
                    "Your balance changed and you can no longer afford this bid "
                    f"(balance: {format_currency(buyer.money, False)}, bid: {format_currency(amount, False)})."
                )
            buyer.money = F("money") - amount
            buyer.save(update_fields=["money"])
            AuctionOffer.objects.create(listing=listing, buyer=buyer, amount=amount)

    @bid.autocomplete("listing_id")
    async def bid_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        qs = (
            AuctionListing.objects.filter(server_id=interaction.guild_id, status=AuctionListing.Status.ACTIVE)
            .select_related("instance")
            .order_by("expires_at")[:25]
        )
        return [
            app_commands.Choice(
                name=f"#{listing.id} {listing.instance.short_description()} — "
                f"{format_currency(listing.asking_price)}",
                value=listing.id,
            )
            async for listing in qs
        ]

    # -- /auction mybids ------------------------------------------------------------------------

    @app_commands.command(name="mybids")
    async def my_bids(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        See your pending bids and cancel any of them.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        buyer, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        offers = [
            offer
            async for offer in AuctionOffer.objects.filter(buyer=buyer, status=AuctionOffer.Status.PENDING)
            .select_related("listing", "listing__instance")
            .order_by("-created_at")[:25]
        ]
        if not offers:
            await interaction.followup.send("You don't have any pending bids.")
            return

        embed = discord.Embed(title="Your pending bids", color=AUCTION_COLOR)
        for offer in offers:
            embed.add_field(
                name=f"Bid #{offer.id} — {format_currency(offer.amount, False, self.bot)}",
                value=f"Listing #{offer.listing_id}: {offer.listing.instance.short_description()}",
                inline=False,
            )
        view = views.CancelOfferView(interaction, offers, self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def cancel_offer(self, offer_id: int, buyer_discord_id: int) -> AuctionOffer:
        return await sync_to_async(self._cancel_offer)(offer_id, buyer_discord_id)

    def _cancel_offer(self, offer_id: int, buyer_discord_id: int) -> AuctionOffer:
        with transaction.atomic():
            try:
                offer = AuctionOffer.objects.select_related("buyer").select_for_update().get(pk=offer_id)
            except AuctionOffer.DoesNotExist:
                raise RuntimeError("This bid no longer exists.")
            if offer.buyer.discord_id != buyer_discord_id:
                raise RuntimeError("This isn't your bid.")
            if offer.status != AuctionOffer.Status.PENDING:
                raise RuntimeError("This bid is no longer pending.")

            buyer = offer.buyer
            buyer.money = F("money") + offer.amount
            buyer.save(update_fields=["money"])
            offer.status = AuctionOffer.Status.CANCELLED
            offer.save(update_fields=["status"])
            return offer

    # -- /auction mylistings ------------------------------------------------------------------------

    @app_commands.command(name="mylistings")
    async def my_listings(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        See your active listings and the highest bid on each — accept or reject it.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        seller, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        listings = [
            listing
            async for listing in AuctionListing.objects.filter(
                seller=seller, status=AuctionListing.Status.ACTIVE
            )
            .select_related("instance")
            .prefetch_related("offers")
            .order_by("expires_at")
        ]
        if not listings:
            await interaction.followup.send("You don't have any active listings.")
            return

        embed = discord.Embed(
            title="Your listings",
            description="You only ever see the highest bid on each listing — the bidder stays anonymous "
            "until you accept.",
            color=AUCTION_COLOR,
        )
        top_offers = []
        for listing in listings:
            pending = [o for o in listing.offers.all() if o.status == AuctionOffer.Status.PENDING]
            if pending:
                top = max(pending, key=lambda o: o.amount)
                top_offers.append(top)
                value = f"Highest bid: **{format_currency(top.amount, False, self.bot)}**"
            else:
                value = "No bids yet."
            embed.add_field(
                name=(
                    f"Listing #{listing.id} — {listing.instance.short_description()} "
                    f"(asking {format_currency(listing.asking_price, False, self.bot)})"
                ),
                value=value,
                inline=False,
            )

        if not top_offers:
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        view = views.ListingOffersView(interaction, top_offers, self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def accept_offer(self, offer_id: int, seller_discord_id: int) -> tuple[AuctionListing, AuctionOffer]:
        return await sync_to_async(self._accept_offer)(offer_id, seller_discord_id)

    def _accept_offer(self, offer_id: int, seller_discord_id: int) -> tuple[AuctionListing, AuctionOffer]:
        with transaction.atomic():
            try:
                offer = (
                    AuctionOffer.objects.select_related("listing", "listing__instance", "listing__seller", "buyer")
                    .select_for_update()
                    .get(pk=offer_id)
                )
            except AuctionOffer.DoesNotExist:
                raise RuntimeError("This bid no longer exists.")
            listing = offer.listing
            if listing.seller.discord_id != seller_discord_id:
                raise RuntimeError("This isn't your listing.")
            if listing.status != AuctionListing.Status.ACTIVE or offer.status != AuctionOffer.Status.PENDING:
                raise RuntimeError("This bid is no longer available.")

            seller = listing.seller
            seller.money = F("money") + offer.amount
            seller.save(update_fields=["money"])

            instance = listing.instance
            instance.player = offer.buyer
            instance.locked = None
            instance.save(update_fields=["player", "locked"])

            offer.status = AuctionOffer.Status.ACCEPTED
            offer.save(update_fields=["status"])
            listing.status = AuctionListing.Status.SOLD
            listing.save(update_fields=["status"])

            others = AuctionOffer.objects.filter(listing=listing, status=AuctionOffer.Status.PENDING).exclude(
                pk=offer.pk
            )
            for other in others.select_related("buyer"):
                other_buyer = other.buyer
                other_buyer.money = F("money") + other.amount
                other_buyer.save(update_fields=["money"])
                other.status = AuctionOffer.Status.REFUNDED
                other.save(update_fields=["status"])

            return listing, offer

    async def reject_offer(self, offer_id: int, seller_discord_id: int) -> AuctionOffer:
        return await sync_to_async(self._reject_offer)(offer_id, seller_discord_id)

    def _reject_offer(self, offer_id: int, seller_discord_id: int) -> AuctionOffer:
        with transaction.atomic():
            try:
                offer = (
                    AuctionOffer.objects.select_related("listing__seller", "buyer").select_for_update().get(pk=offer_id)
                )
            except AuctionOffer.DoesNotExist:
                raise RuntimeError("This bid no longer exists.")
            if offer.listing.seller.discord_id != seller_discord_id:
                raise RuntimeError("This isn't your listing.")
            if offer.status != AuctionOffer.Status.PENDING:
                raise RuntimeError("This bid is no longer pending.")

            buyer = offer.buyer
            buyer.money = F("money") + offer.amount
            buyer.save(update_fields=["money"])
            offer.status = AuctionOffer.Status.REJECTED
            offer.save(update_fields=["status"])
            return offer

    # -- /auction shop & /auction buy ------------------------------------------------------------------------

    @app_commands.command(name="shop")
    @app_commands.describe(name="Only show items whose treasure name contains this", sort="How to order the results")
    @app_commands.choices(sort=SORT_CHOICES)
    async def shop(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        name: str | None = None,
        sort: app_commands.Choice[str] | None = None,
    ):
        """
        Browse Buggy's Auction House resale shop on this server.

        Parameters
        ----------
        name: str
            Only show items whose treasure name contains this.
        sort: str
            How to order the results.
        """
        await interaction.response.defer(thinking=True)
        server_id = interaction.guild_id
        auction_settings = await AuctionSettings.aload()
        qs = HotelStock.objects.filter(server_id=server_id, status=HotelStock.Status.AVAILABLE).select_related(
            "instance", "instance__ball"
        )
        if auction_settings.max_shop_rarity is not None:
            qs = qs.filter(instance__ball__rarity__lte=auction_settings.max_shop_rarity)
        if name:
            qs = qs.filter(instance__ball__country__icontains=name)
        order = _STOCK_SORT_FIELDS.get(sort.value if sort else "", "resale_price")
        stock = [item async for item in qs.order_by(order)]
        if not stock:
            await interaction.followup.send(
                "No items match that name." if name else "Buggy doesn't have anything for sale on this server right now."
            )
            return

        booster = await self._get_booster_role(interaction.user, server_id, "buy_discount_percent")
        discount_percent = booster.buy_discount_percent if booster else 0

        entries = []
        for item in stock:
            price = item.resale_price
            if discount_percent:
                price = round(price * (1 - discount_percent / 100))
            entries.append(
                (
                    f"#{item.id} — {item.instance.description(include_emoji=True, bot=self.bot)}",
                    format_currency(price, False, self.bot),
                )
            )
        source = FieldPageSource(entries, per_page=8, inline=False)
        source.embed.title = "Buggy's Auction House — Resale shop"
        source.embed.colour = AUCTION_COLOR
        pages = Pages(source, interaction=interaction, compact=True)
        await pages.start()

    @app_commands.command(name="buy")
    @app_commands.rename(stock_id="item")
    async def buy(self, interaction: discord.Interaction["BallsDexBot"], stock_id: int):
        """
        Buy a treasure from Buggy's Auction House resale shop.

        Parameters
        ----------
        stock_id: int
            The item you want to buy.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)
        server_id = interaction.guild_id
        try:
            stock = await HotelStock.objects.select_related("instance", "instance__ball").aget(
                pk=stock_id, server_id=server_id
            )
        except HotelStock.DoesNotExist:
            await interaction.followup.send("This item doesn't exist in this server's shop.")
            return
        if stock.status != HotelStock.Status.AVAILABLE:
            await interaction.followup.send("This item has already been sold.")
            return

        auction_settings = await AuctionSettings.aload()
        if (
            auction_settings.max_shop_rarity is not None
            and stock.instance.countryball.rarity > auction_settings.max_shop_rarity
        ):
            await interaction.followup.send("This item isn't part of Buggy's current shop selection.")
            return

        buyer, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        booster = await self._get_booster_role(interaction.user, server_id, "buy_discount_percent")
        price = stock.resale_price
        if booster:
            price = round(price * (1 - booster.buy_discount_percent / 100))
        if not buyer.can_afford(price):
            await interaction.followup.send(
                f"You don't have enough {settings.currency_display_plural(self.bot)} for this item.\n"
                f"Your balance: **{format_currency(buyer.money, False, self.bot)}** • "
                f"Price: **{format_currency(price, False, self.bot)}**"
            )
            return

        try:
            await sync_to_async(self._settle_shop_purchase)(stock.pk, buyer.pk, price)
        except RuntimeError as error:
            await interaction.followup.send(str(error))
            return
        await interaction.followup.send(f"Bought for **{format_currency(price, False, self.bot)}**!", ephemeral=True)

    def _settle_shop_purchase(self, stock_id: int, buyer_id: int, price: int):
        with transaction.atomic():
            stock = HotelStock.objects.select_related("instance").select_for_update().get(pk=stock_id)
            if stock.status != HotelStock.Status.AVAILABLE:
                raise RuntimeError("This item has already been sold.")
            buyer = Player.objects.select_for_update().get(pk=buyer_id)
            if buyer.money < price:
                raise RuntimeError(
                    "You don't have enough coins anymore "
                    f"(balance: {format_currency(buyer.money, False)}, price: {format_currency(price, False)})."
                )
            buyer.money = F("money") - price
            buyer.save(update_fields=["money"])
            instance = stock.instance
            instance.player = buyer
            instance.save(update_fields=["player"])
            stock.status = HotelStock.Status.SOLD
            stock.save(update_fields=["status"])

    @buy.autocomplete("stock_id")
    async def buy_autocomplete(
        self, interaction: discord.Interaction["BallsDexBot"], current: str
    ) -> list[app_commands.Choice[int]]:
        auction_settings = await AuctionSettings.aload()
        qs = HotelStock.objects.filter(server_id=interaction.guild_id, status=HotelStock.Status.AVAILABLE)
        if auction_settings.max_shop_rarity is not None:
            qs = qs.filter(instance__ball__rarity__lte=auction_settings.max_shop_rarity)
        qs = qs.select_related("instance").order_by("resale_price")[:25]
        return [
            app_commands.Choice(
                name=f"#{item.id} {item.instance.short_description()} — {format_currency(item.resale_price)}",
                value=item.id,
            )
            async for item in qs
        ]

    # -- activity tracking (for giveaway eligibility) ------------------------------------------

    @commands.Cog.listener()
    async def on_app_command_completion(
        self, interaction: discord.Interaction["BallsDexBot"], command: app_commands.Command | app_commands.ContextMenu
    ):
        if interaction.guild_id is None:
            return
        await sync_to_async(self._touch_activity)(interaction.user.id, interaction.guild_id)

    def _touch_activity(self, discord_id: int, server_id: int):
        player, _ = Player.objects.get_or_create(discord_id=discord_id)
        ServerActivity.objects.update_or_create(player=player, server_id=server_id)

    # -- background loops ------------------------------------------------------------------------

    @tasks.loop(minutes=5)
    async def sweep_listings(self):
        await sync_to_async(self._sweep_listings)()

    @sweep_listings.before_loop
    async def before_sweep_listings(self):
        await self.bot.wait_until_ready()

    def _sweep_listings(self):
        now = timezone.now()
        with transaction.atomic():
            active = list(
                AuctionListing.objects.select_for_update()
                .filter(status=AuctionListing.Status.ACTIVE)
                .select_related("instance")
            )
            for listing in active:
                if listing.expires_at <= now:
                    self._expire_listing(listing)
                else:
                    listing.instance.locked = now
                    listing.instance.save(update_fields=["locked"])

    def _expire_listing(self, listing: AuctionListing):
        listing.status = AuctionListing.Status.EXPIRED
        listing.save(update_fields=["status"])
        listing.instance.locked = None
        listing.instance.save(update_fields=["locked"])
        pending = AuctionOffer.objects.filter(listing=listing, status=AuctionOffer.Status.PENDING).select_related(
            "buyer"
        )
        for offer in pending:
            buyer = offer.buyer
            buyer.money = F("money") + offer.amount
            buyer.save(update_fields=["money"])
            offer.status = AuctionOffer.Status.REFUNDED
            offer.save(update_fields=["status"])

    @tasks.loop(hours=1)
    async def giveaway_draw(self):
        await sync_to_async(self._giveaway_draw)()

    @giveaway_draw.before_loop
    async def before_giveaway_draw(self):
        await self.bot.wait_until_ready()

    def _giveaway_draw(self):
        auction_settings = AuctionSettings.load()
        cutoff = timezone.now() - timedelta(hours=auction_settings.giveaway_interval_hours)
        activity_cutoff = timezone.now() - timedelta(hours=auction_settings.giveaway_activity_window_hours)

        server_ids = (
            HotelStock.objects.filter(status=HotelStock.Status.AVAILABLE)
            .values_list("server_id", flat=True)
            .distinct()
        )
        for server_id in server_ids:
            last = GiveawayLog.objects.filter(server_id=server_id).order_by("-drawn_at").first()
            if last is not None and last.drawn_at > cutoff:
                continue

            eligible_ids = list(
                ServerActivity.objects.filter(server_id=server_id, last_seen__gte=activity_cutoff).values_list(
                    "player_id", flat=True
                )
            )
            if not eligible_ids:
                continue
            stock_ids = list(
                HotelStock.objects.filter(server_id=server_id, status=HotelStock.Status.AVAILABLE).values_list(
                    "pk", flat=True
                )
            )
            if not stock_ids:
                continue

            winner_player_id = random.choice(eligible_ids)
            stock_id = random.choice(stock_ids)

            with transaction.atomic():
                stock = HotelStock.objects.select_related("instance").select_for_update().get(pk=stock_id)
                if stock.status != HotelStock.Status.AVAILABLE:
                    continue
                winner = Player.objects.get(pk=winner_player_id)
                instance = stock.instance
                instance.player = winner
                instance.save(update_fields=["player"])
                stock.status = HotelStock.Status.GIVEN_AWAY
                stock.save(update_fields=["status"])
                GiveawayLog.objects.create(server_id=server_id, winner=winner, instance=instance)
