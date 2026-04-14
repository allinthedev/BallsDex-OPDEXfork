import logging
import random
from typing import TYPE_CHECKING

import discord
from discord.ui import Select, select
from tortoise.exceptions import BaseORMException, DoesNotExist

from ballsdex.core.currency_models import CurrencySettings, MoneyInstance
from ballsdex.core.merchant_models import GlobalShop, MerchantItem
from ballsdex.core.models import BallInstance, Player
from ballsdex.core.utils.menus import ListPageSource
from ballsdex.core.utils.paginator import Pages
from tortoise.timezone import now as tortoise_now

from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)

class BuyItemSource(ListPageSource):
    def __init__(self, entries: list[MerchantItem]):
        super().__init__(entries, per_page=25)

    async def format_page(self, menu, items):
        menu.set_options(items)
        return True  # signal to edit the page

class BuyItemView(Pages):
    def __init__(self, interaction: discord.Interaction["BallsDexBot"], shop: GlobalShop, items: list[MerchantItem]):
        self.bot = interaction.client
        self.shop = shop
        source = BuyItemSource(items)
        super().__init__(source, interaction=interaction)
        self.add_item(self.buy_item_select)

    def set_options(self, items: list[MerchantItem]):
        options: list[discord.SelectOption] = []
        for item in items:
            options.append(
                discord.SelectOption(
                    label=item.name, 
                    description=f"Prize: {item.prize if item.prize else 'Free'}", 
                    value=str(item.pk)
                )
            )
        self.buy_item_select.options = options

    @select(placeholder="Select an item to buy")
    async def buy_item_select(self, interaction: discord.Interaction["BallsDexBot"], select: Select):
        value = int(select.values[0])
        item = await MerchantItem.get(pk=value)
        if not item.enabled:
            await interaction.response.send_message("This item isn't enabled.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)

        currency_settings = await self.get_currency_settings()

        try:
            player = await Player.get(discord_id=interaction.user.id)
            money_instance = await MoneyInstance.get(player=player)
        except DoesNotExist:
            await interaction.response.send_message("You're not registred in the economy system yet.")
            return

        if not item.prize:
            instance = await BallInstance.create(
                player=player,
                ball=item.cached_ball,
                special=item.cached_special,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                catch_date=tortoise_now(),
                server_id=interaction.guild_id,
            )
            await interaction.followup.send(
                f"You've bought {item.name} for **free!**\n"
                f"{instance.description(include_emoji=True, bot=self.bot)}"
            )
            return

        if money_instance.amount < item.prize:
            currency_emoji = (
                self.bot.get_emoji(currency_settings.emoji_id) 
                if currency_settings.emoji_id 
                else ""
            )
            await interaction.followup.send(
                f"You don't enough {currency_emoji} {currency_settings.name} to buy "
                f"**{item.name}**\n"
                f"Your actual balance: {await self.format_price(money_instance.amount)}"
            )
            return

        try:
            instance = await BallInstance.create(
                player=player,
                ball=item.cached_ball,
                special=item.cached_special,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                catch_date=tortoise_now(),
                server_id=interaction.guild_id,
            )
        except BaseORMException:
            log.exception("Failed to create a ball instance while a user trying to buy an item.", exc_info=True)
            await interaction.followup.send("An error occurred while trying to buy the item.")
            return
        else:
            money_instance.amount -= item.prize
            await money_instance.save(update_fields=("amount",))
            await interaction.followup.send(
                f"You've bought {item.name} for **{await self.format_price(item.prize)}!**\n"
                f"{instance.description(include_emoji=True, bot=self.bot)}"
            )
            return

    async def format_price(self, amount: int | None, include_emoji: bool = True):
        currency_settings = await self.get_currency_settings()
        text = f"{amount:,} {currency_settings.display_name(amount)}" if amount else "Free"
        if include_emoji:
            emoji = self.bot.get_emoji(currency_settings.emoji_id)
            if emoji:
                text = f"{emoji} {text}"
        return text

    async def get_currency_settings(self):
        return await CurrencySettings.load()