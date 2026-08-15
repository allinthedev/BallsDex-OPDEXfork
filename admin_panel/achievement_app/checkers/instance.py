import logging

import discord
from asgiref.sync import async_to_sync
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from achievement_app import models
from achievement_app.models import AchievementType, notify_user, progress_achievement
from bd_models.models import BallInstance, GuildConfig, Player

logger = logging.getLogger(__name__)


@receiver(post_save, sender=BallInstance)
def on_instance_saved(sender, instance: BallInstance, created: bool, **kwargs):
    transaction.on_commit(lambda: async_to_sync(_handle_created_ballinstance)(instance))


async def _handle_created_ballinstance(instance: BallInstance, notify: bool = True):
    unlocked = []
    player = await Player.objects.aget(pk=instance.player_id)
    unlocked += await progress_achievement(player, AchievementType.FIRST_CATCH)
    unlocked += await progress_achievement(player, AchievementType.COMPLETE_GROUP)
    unlocked += await progress_achievement(player, AchievementType.COMPLETION_PERCENTAGE)
    unlocked += await progress_achievement(player, AchievementType.CATCH_BALL, instance=instance)
    if instance.catch_date and instance.spawned_time:
        unlocked += await progress_achievement(
            player,
            AchievementType.FASTEST_CATCHER,
            elapsed_seconds=(instance.catch_date - instance.spawned_time).total_seconds(),
        )
    if instance.specialcard is not None:
        unlocked += await progress_achievement(player, AchievementType.FIRST_SPECIAL, special=instance.specialcard)
    unlocked += await progress_achievement(player, AchievementType.PLAYTIME)
    unlocked += await progress_achievement(player, AchievementType.BALL_COUNT)
    if instance.trade_player_id is not None:
        trade_player = await Player.objects.aget(pk=instance.trade_player_id)
        unlocked += await progress_achievement(player, AchievementType.RECEIVE_BALL, user_id=trade_player.discord_id)
    if instance.favorite:
        unlocked += await progress_achievement(player, AchievementType.FIRST_FAVORITE_BALL)

    if unlocked and notify and models._BOT is not None:
        user = await models._BOT.fetch_user(player.discord_id)
        channel = None
        try:
            catch_channel_id = getattr(instance, "_catch_channel_id", None)
            if catch_channel_id:
                channel = models._BOT.get_channel(catch_channel_id) or await models._BOT.fetch_channel(
                    catch_channel_id
                )
            elif instance.server_id:
                config = await GuildConfig.objects.aget_or_none(guild_id=instance.server_id)
                if config and config.spawn_channel:
                    guild = await models._BOT.fetch_guild(instance.server_id)
                    channel = await guild.fetch_channel(config.spawn_channel)
        except (discord.HTTPException, discord.Forbidden):
            channel = None
        await notify_user(unlocked, user=user, channel=channel)  # type: ignore

    return unlocked
