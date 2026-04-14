import base64
import random
import requests
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from discord.ext import commands
from tortoise.queryset import QuerySet

from ballsdex.core.collector_models import (
    Collector as CollectorModel,
    CollectorInstance, 
    CollectorRequirement
)
from ballsdex.core.models import BallInstance, Player
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.settings import settings
from tortoise.timezone import now as tortoise_now, get_default_timezone

from .transformers import CollectorEnabledTransform

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

class Collector(commands.GroupCog):
    """
    Claim your collector card!
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def claim(self, interaction: discord.Interaction["BallsDexBot"], collector: CollectorEnabledTransform):
        """
        Claim a collector card.

        Parameters
        ----------
        collector: Collector
            The collector to claim.
        """
        player, _ = await Player.get_or_create(discord_id=interaction.user.id)
        if await CollectorInstance.filter(player=player, collector=collector).exists():
            await interaction.response.send_message("You've claimed this collector card!", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        requirements = await collector.requirements.all()
        if not requirements:
            instance = await BallInstance.create(
                player=player,
                ball=collector.cached_ball,
                health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                attack_bonus=random.randint(settings.max_attack_bonus, settings.max_attack_bonus),
                special=collector.cached_special,
                tradeable=collector.tradeable,
                catch_date=tortoise_now()
            )

            await CollectorInstance.create(player=player, collector=collector)
            await interaction.followup.send(
                f"You've claimed **{collector.name}** collector!\n"
                f"{instance.description(include_emoji=True, bot=self.bot)}"
            )
            return
        
        qs = BallInstance.filter(player=player).order_by("-catch_date")
        result = await self._check_requirements(qs, requirements)
        if isinstance(result, tuple):
            result, msg = result
            await interaction.followup.send(msg)
            return
        
        instance = await BallInstance.create(
            player=player,
            ball=collector.cached_ball,
            health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
            attack_bonus=random.randint(settings.max_attack_bonus, settings.max_attack_bonus),
            special=collector.cached_special,
            tradeable=collector.tradeable,
            catch_date=tortoise_now()
        )

        await CollectorInstance.create(player=player, collector=collector)
        await interaction.followup.send(
            f"You've claimed **{collector.name}** collector!\n"
            f"{instance.description(include_emoji=True, bot=self.bot)}"
        )
        return
    
    @app_commands.command(name="list")
    async def collector_list(self, interaction: discord.Interaction["BallsDexBot"]):
        """
        Check all active collectors.
        """
        await interaction.response.defer(thinking=True)
        collectors = [
            x 
            for x in await CollectorModel.all().prefetch_related("requirements")
            if (x.start_date or datetime.min.replace(tzinfo=get_default_timezone()))
            <= tortoise_now()
            <= (x.end_date or datetime.max.replace(tzinfo=get_default_timezone()))
        ]
        
        if not collectors:
            await interaction.followup.send(
                f"{settings.bot_name} doesn't have any collectors active.",
                ephemeral=True
            )
            return
        
        entries: list[tuple[str, str]] = []
        for collector in collectors:
            description = (
                f"Collector {settings.collectible_name}: {collector.cached_ball}\n\n"
            )
            i = 1
            async for requirement in collector.requirements.all():
                desc_requirement = (
                    f"**Requirement #{i}:**\n"
                    f"Amount: {requirement.amount}\n"
                )
                if requirement.cached_ball:
                    desc_requirement += f"{settings.collectible_name.title()}: {requirement.cached_ball.country}\n"
                if requirement.cached_special:
                    desc_requirement += f"Special: {requirement.cached_special.name}\n"
                description += desc_requirement

            entries.append((f"{collector.name}", description))
        source = FieldPageSource(entries, per_page=3)
        source.embed.title = "Active Collector List"

        pages = Pages(source, interaction=interaction)
        await pages.start()
    
    @commands.group()
    async def collector(self, ctx: commands.Context["BallsDexBot"]):
        pass

    @collector.command()
    @commands.is_owner()
    async def update(self, ctx: commands.Context["BallsDexBot"]):
        """
        Update Collector package.
        """
        link = "https://api.github.com/repos/Valen7440/Collector/contents/updater.py"

        request = requests.get(link, {"ref": "master"})

        match request.status_code:
            case requests.codes.not_found:
                await ctx.send("Could not find updater for the master branch.")

            case requests.codes.ok:
                content = requests.get(link, {"ref": "master"}).json()["content"]

                await ctx.invoke(
                    self.bot.get_command("eval"), body=base64.b64decode(content).decode() # type: ignore
                )

            case _:
                await ctx.send(f"Request raised error code `{request.status_code}`.")

    async def _check_requirements(
        self, balls: QuerySet[BallInstance], requirements: list[CollectorRequirement]
    ) -> Literal[True] | tuple[Literal[False], str]:
        for i, requirement in enumerate(requirements, start=1):
            qs = balls
            text = ""
            if requirement.cached_ball:
                qs = qs.filter(ball=requirement.cached_ball)
                text += f"{requirement.cached_ball.country} "
            if requirement.cached_special:
                qs = qs.filter(special=requirement.cached_special)
                text += f"{requirement.cached_special.name}"
            count = await qs.count()
            if not count > requirement.amount:
                grammar = (
                    settings.collectible_name
                    if count == 1
                    else settings.plural_collectible_name
                )
                return (
                    False, 
                    f"You don't meet requirement #{i}: **X{requirement.amount} "
                    f"{text if text else grammar}**"
                )
            if requirement.delete_balls:
                ids = await qs.limit(requirement.amount).values_list("id", flat=True)
                await BallInstance.filter(id__in=ids).update(deleted=True)

        return True
