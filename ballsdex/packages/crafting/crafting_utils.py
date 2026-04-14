import discord
from typing import Dict, List, Optional
import random

from .models import CraftingRecipe
from .models import CraftingIngredient
from .models import CraftingIngredientGroup                                            
from .models import CraftingGroupOption

from ballsdex.settings import settings                                       
from ballsdex.core.utils.transformers import BallEnabledTransform, BallTransform        
from ballsdex.core.utils.transformers import SpecialEnabledTransform
from ballsdex.settings import settings                  
                                
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
    can_craft_recipe
)

from .crafting_views import CraftingView 

from .session_manager import crafting_sessions
 
async def update_crafting_display(interaction, user_id, is_new=False):
    """Update the crafting session display using followup (for when we already responded)."""
    session = crafting_sessions[user_id]
    
    # Get ball instances data
    ball_instances = []
    if session['ingredient_instances']:
        try:
            ball_instances = await BallInstance.filter(
                id__in=session['ingredient_instances']
            ).prefetch_related('ball', 'special').all()
        except Exception as e:
            print(f"Error fetching ball instances: {e}")
            return
    
    # Find possible recipes
    possible_recipes = await find_matching_recipes(session['ingredient_instances'])
    
    embed = discord.Embed(
        title="🔨 Crafting Session",
        color=0x0099ff
    )
    
    # Show possible results
    if possible_recipes:
        results = []
        for recipe in possible_recipes[:5]:  # Show max 5
            emoji = interaction.client.get_emoji(recipe.result.emoji_id)
            special_prefix = f"{session['special'].emoji} " if session['special'] else ""
            results.append(f"{emoji} {special_prefix}{recipe.result.country}")
        
        embed.add_field(
            name="✅ Can Craft",
            value="\n".join(results) + (f"\n*+{len(possible_recipes)-5} more*" if len(possible_recipes) > 5 else ""),
            inline=False
        )
    else:
        embed.add_field(
            name="❓ Can Craft",
            value="*Add ingredients to see possible recipes*\nUse `/craft recipes` to view all available recipes",
            inline=False
        )
    
    # Show current ingredients (with IDs and stats)
    if ball_instances:
        ingredients_display = []
        for instance in ball_instances:
            emoji = interaction.client.get_emoji(instance.ball.emoji_id)
            special_text = f"{instance.special.emoji} " if instance.special else ""
            stats_text = f"(ATK: {instance.attack_bonus:+d}, HP: {instance.health_bonus:+d})"
            ingredients_display.append(f"{emoji} {special_text}{instance.ball.country} #{instance.pk:0X} {stats_text}")
        
        embed.add_field(
            name="Current Ingredients",
            value="\n".join(ingredients_display),
            inline=False
        )
    else:
        embed.add_field(
            name="Current Ingredients",
            value="*No ingredients added yet*\nUse `/craft add` to add ingredients",
            inline=False
        )
    
    # Show total stats that will be sacrificed
    if ball_instances:
        total_attack = sum(instance.attack_bonus for instance in ball_instances) 
        total_health = sum(instance.health_bonus for instance in ball_instances)
        embed.add_field(
            name="Total Stats of all ingredients",
            value=f"**ATK:** {total_attack:+d} | **HP:** {total_health:+d}",
            inline=False
        )
    
    # Show commands help
    embed.add_field(
        name="Commands",
        value="`/craft add` - Add specific instance\n"
              "`/craft remove` - Remove specific instance\n"
              "`/craft clear` - Clear all ingredients\n"
              "`/craft recipes` - View available recipes",
        inline=False
    )
    
    special_text = f"\n🌟 **Special:** {session['special'].emoji} {session['special'].name}" if session['special'] else ""
    embed.set_footer(text=f"Session expires in 10 minutes{special_text}")
    
    view = CraftingView(interaction.client, session['player'], session)
    
    # Find and edit the original crafting message

    if is_new:
        message = await interaction.followup.send("Crafting session:", embed=embed, view=view)
        session['message'] = message
        return  # skip the rest
        
    try:
        if 'message' in session and session['message']:
            await session['message'].edit(embed=embed, view=view)
        else:
            # Fallback: try to find the message in recent history
            channel = interaction.channel
            async for message in channel.history(limit=50):
                if (message.author == interaction.client.user and 
                    message.embeds and 
                    message.embeds[0].title == "🔨 Crafting Session"):
                    await message.edit(embed=embed, view=view)
                    # Store the message reference for future use
                    session['message'] = message
                    break
            else:
                # If we can't find the original, send a new message
                new_message = await interaction.followup.send("Updated crafting session:", embed=embed, view=view)
                session['message'] = new_message
    except Exception as e:
        print(f"Error updating crafting display: {e}")
        # If we can't edit the original, send a new message
        try:
            new_message = await interaction.followup.send("Updated crafting session:", embed=embed, view=view)
            session['message'] = new_message
        except Exception as e2:
            print(f"Error sending followup message: {e2}")

