import discord
from discord import TYPE_CHECKING, app_commands
from tortoise.functions import Count

from ballsdex.core.models import BallInstance, Player
from ballsdex.core.utils.buttons import ConfirmChoiceView
from ballsdex.core.utils.transformers import BallEnabledTransform, BallInstanceTransform, SpecialEnabledTransform
from ballsdex.packages.countryballs.countryball import BallSpawnView
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

medals = {1: "🥇", 2: "🥈", 3: "🥉"}

@app_commands.command()
@app_commands.checks.cooldown(1, 240, key=lambda i: i.user.id)
async def drop(interaction: discord.Interaction["BallsDexBot"], countryball: BallInstanceTransform):
    """
    Drop a countryball from your inventory.

    Parameters
    ----------
    countryball: BallInstance
        The ball you want to drop
    """
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("This channel isn't a text channel.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    description = countryball.description(include_emoji=True, bot=interaction.client)
    view = ConfirmChoiceView(
        interaction, 
        accept_message=f"Confirmed, dropping {description}...",
        cancel_message="Request cancelled."
    )
    await interaction.followup.send(
        f"Are you sure you want to drop {description}?",
        view=view,
        ephemeral=True
    )
    await view.wait()
    if not view.value:
        return

    await countryball.fetch_related("ball")

    ball_view = await BallSpawnView.from_existing(interaction.client, countryball)
    await ball_view.spawn(channel)

@app_commands.command()
async def leaderboard(
    interaction: discord.Interaction["BallsDexBot"], 
    countryball: BallEnabledTransform | None = None,
    special: SpecialEnabledTransform | None = None,
):
    """
    Check the top 10 players with the most countryballs.

    Parameters
    ----------
    countryball: Ball | None
        Filter the result by a specific countryball
    special: Special | None
        Filter the result by a specific special
    """
    filters = {}
    if special:
        filters["special"] = special
    if countryball:
        filters["ball"] = countryball

    query = (
        BallInstance
        .filter(**filters)
        .group_by("player_id")
        .annotate(ball_count=Count("id"))
        .order_by("-ball_count")
        .limit(10)
    )
    values = await query.values("ball_count", "player_id")
    if not values:
        await interaction.response.send_message("No players found.", ephemeral=True)
        return

    player_ids = [x["player_id"] for x in values]

    players_qs = await Player.filter(id__in=player_ids)
    players = {p.pk: p for p in players_qs}
    instances = [
        {
            "player": players[x["player_id"]], 
            "ball_count": x["ball_count"]
        } 
        for x in values
    ]

    await interaction.response.defer(thinking=True)
    text = ""

    for i, instance in enumerate(instances, start=1):
        player = instance["player"]
        user = interaction.client.get_user(player.discord_id)
        if not user:
            user = await interaction.client.fetch_user(player.discord_id)
        
        medal = medals.get(i, i)

        count = instance["ball_count"]
        grammar = settings.collectible_name if count == 1 else settings.plural_collectible_name
        text += f"{medal}. {user.display_name} - {grammar}: {count}\n"

    ball_txt = countryball.country if countryball else ""
    special_txt = special.name if special else ""

    combined = " ".join([str(x) for x in [ball_txt, special_txt] if x])
    title = f"Top 10 players of {settings.bot_name}"
    if combined:
        title = f"{title} ({combined})"
    embed = discord.Embed(
        title=title,
        color=discord.Color.blurple(),
    )
    embed.description = text
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    await interaction.followup.send(embed=embed)

# add all app_commands to this list, because it'll use in the startup
commands: list[app_commands.Command] = [drop, leaderboard]