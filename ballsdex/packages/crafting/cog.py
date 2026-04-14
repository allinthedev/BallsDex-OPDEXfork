import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from discord.ui import Button, View
from typing import TYPE_CHECKING
import random
from typing import Dict, List, Optional
 
from .models import CraftingRecipe
from .models import CraftingIngredient
from .models import CraftingIngredientGroup
from .models import CraftingGroupOption

from ballsdex.core.utils.transformers import BallEnabledTransform
from ballsdex.core.utils.transformers import BallInstanceTransform
from ballsdex.core.utils.transformers import SpecialEnabledTransform, TradeCommandType
from ballsdex.core.bot import BallsDexBot
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

from ballsdex.core.models import (
    Ball,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    GuildConfig,
    Player,
    Trade,
    TradeObject,
    balls,
    specials,
)
from .logic import (
    find_matching_recipes, 
    determine_ingredient_usage, 
    can_craft_recipe, 
)
from .crafting_views import CraftingView, RecipeSelect
from .session_manager import crafting_sessions

class Craft(commands.GroupCog):
    def __init__(self, bot):
        self.bot = bot
        self.settings = settings
        # In-memory storage for crafting sessions (you might want to use Redis or database)
        
    @app_commands.command(name="begin", description="Start a crafting session.")
    async def craft_begin(self, interaction: discord.Interaction, special: Optional[SpecialEnabledTransform] = None):
        await interaction.response.defer()
        
        user_id = interaction.user.id
        
        if user_id in crafting_sessions:
            await interaction.followup.send(
                "You already have an active crafting session. Please finish or cancel it before starting a new one.",
                ephemeral=True
            )
            return
        player, _ = await Player.get_or_create(discord_id=user_id)

        crafting_sessions[user_id] = {
            'player': player,
            'ingredient_instances': [],
            'special': special,
            'started_at': discord.utils.utcnow(),
            'message': None
        }

        await update_crafting_display(interaction, user_id, is_new=True)

    @app_commands.command(name="add", description="Add a countryball to crafting session")
    async def craft_add(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id

        # Inside /craft add command, after fetching ball_instance
        await countryball.fetch_related("ball", "special")
        
        # Check if ball is involved in a trade
        # Reject if ball is involved in a trade, even if unconfirmed
        if await countryball.is_locked():
            return await interaction.followup.send(
                f"❌ This countryball is currently reserved in a trade and can’t be used for crafting.",
                ephemeral=True
            )
            
        if user_id not in crafting_sessions:
            return await interaction.followup.send("❌ Start a crafting session first with `/craft begin`.", ephemeral=True)

        session = crafting_sessions[user_id]
        player = session['player']

        if countryball.player_id != player.pk:
            return await interaction.followup.send("❌ You don't own this countryball!", ephemeral=True)

        if session['special'] and countryball.special_id != session['special'].pk:
            return await interaction.followup.send(
                f"❌ This ball isn't the right special ({session['special'].name})!", ephemeral=True)

        if not session['special'] and countryball.special_id is not None:
            return await interaction.followup.send("❌ No specials allowed in this session!", ephemeral=True)

        if countryball.pk in session['ingredient_instances']:
            return await interaction.followup.send(f"❌ Already added #{countryball.pk}!", ephemeral=True)

        session['ingredient_instances'].append(countryball.pk) 

        await interaction.followup.send(
                f"Added {countryball.ball.country} #{countryball.pk:0X} to crafting session!",
                ephemeral=True
            )
            
        await update_crafting_display(interaction, user_id)

    @app_commands.command(name="remove", description="Remove a countryball from crafting session")
    async def craft_remove(self, interaction: discord.Interaction, countryball: BallInstanceTransform):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        await countryball.fetch_related("ball", "special") 

        if user_id not in crafting_sessions:
            return await interaction.followup.send("❌ No active crafting session!", ephemeral=True)

        session = crafting_sessions[user_id]
        if countryball.pk not in session['ingredient_instances']:
            return await interaction.followup.send(f"❌ Instance #{countryball.pk:0X} not in your session!", ephemeral=True)

        session['ingredient_instances'].remove(countryball.pk)
        
        await interaction.followup.send(
                f"Removed {countryball.ball.country} #{countryball.pk:0X} from crafting session!",
            )
            
        await update_crafting_display(interaction, user_id)

    @app_commands.command(name="clear", description="clear all added ingredients from crafting session")
    async def craft_clear(self, interaction: discord.Interaction):
        user_id = interaction.user.id

        if user_id not in crafting_sessions:
            return await interaction.response.send_message("❌ No active crafting session!", ephemeral=True)

        crafting_sessions[user_id]['ingredient_instances'] = [] 
        await update_crafting_display(interaction, user_id)

    @app_commands.command(name="recipes", description="show all active crafting recipes")
    async def craft_recipes(self, interaction: discord.Interaction, countryball: Optional[BallEnabledTransform] = None):
        ball = countryball
        
        if ball:
            recipes = await CraftingRecipe.filter(result=ball).all()
            title = f"🔨 Recipes for {ball.country}"
        else:
            recipes = await CraftingRecipe.all().limit(10)
            title = "🔨 Available Recipes (Top 10)"

        if not recipes:
            return await interaction.response.send_message("❌ No recipes found.", ephemeral=True)

        embed = discord.Embed(title=title, color=0x0099ff)

        for recipe in recipes:
            await recipe.fetch_related('result', 'ingredients__ingredient', 'ingredient_groups__options__ball')
            desc = []
            for ing in recipe.ingredients:
                if ing.ingredient:
                    emoji = interaction.client.get_emoji(ing.ingredient.emoji_id)
                    desc.append(f"{emoji} {ing.ingredient.country} x{ing.quantity}")
            for group in recipe.ingredient_groups:
                options = [f"{interaction.client.get_emoji(o.ball.emoji_id)} {o.ball.country}" for o in group.options[:5]]
                desc.append(f"**{group.name}** (choose {group.required_count}): {' | '.join(options)}")
            result_emoji = interaction.client.get_emoji(recipe.result.emoji_id)
            embed.add_field(name=f"{result_emoji} {recipe.result.country}", value="\n".join(desc), inline=False)

        await interaction.response.send_message(embed=embed)

async def update_crafting_display(interaction, user_id, is_new=False):
    from .crafting_utils import update_crafting_display as _update
    await _update(interaction, user_id, is_new)

