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
from ballsdex.core.utils.transformers import BallTransform
from ballsdex.core.utils.transformers import BallInstanceTransform
from ballsdex.core.utils.transformers import SpecialEnabledTransform
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


from .session_manager import crafting_sessions
async def find_matching_recipes(ingredient_instance_ids: List[int]) -> List:
    """Find all recipes that can be crafted with the given ingredient instances."""
    if not ingredient_instance_ids:
        return []
    
    # Get the ball instances and their ball types
    ball_instances = await BallInstance.filter(
        id__in=ingredient_instance_ids
    ).prefetch_related('ball').all()
    
    # Convert to ball type counts
    ball_counts = {}
    for instance in ball_instances:
        ball_id = instance.ball.id
        ball_counts[ball_id] = ball_counts.get(ball_id, 0) + 1
    
    # Get all recipes with their related data
    all_recipes = await CraftingRecipe.all().prefetch_related(
        'ingredients__ingredient',
        'ingredient_groups__options__ball',
        'result'
    )
    
    matching_recipes = []
    
    for recipe in all_recipes:
        if await can_craft_recipe(recipe, ball_counts):
            matching_recipes.append(recipe)
    
    return matching_recipes

async def can_craft_recipe(recipe, available_ball_counts: Dict[int, int]) -> bool:
    """Check if a recipe can be crafted with available ball counts."""
    # Check individual ingredients
    recipe_ingredients = await recipe.ingredients.all()
    for ingredient in recipe_ingredients:
        if ingredient.ingredient_id:  # Only check if ingredient is not None
            required_qty = ingredient.quantity
            available_qty = available_ball_counts.get(ingredient.ingredient_id, 0)
            if available_qty < required_qty:
                return False
    
    # Check ingredient groups
    recipe_groups = await recipe.ingredient_groups.all()
    for group in recipe_groups:
        group_options = await group.options.all()
        available_from_group = 0
        
        for option in group_options:
            available_from_group += available_ball_counts.get(option.ball_id, 0)
        
        if available_from_group < group.required_count:
            return False
    
    return True

async def determine_ingredient_usage(recipe, ingredient_instance_ids: List[int]) -> List[int]:
    """
    Determine which specific ball instances to use for a recipe.
    Returns a list of instance IDs to use.
    """
    # Get the ball instances
    ball_instances = await BallInstance.filter(
        id__in=ingredient_instance_ids
    ).prefetch_related('ball').all()
    
    # Group instances by ball type
    instances_by_ball = {}
    for instance in ball_instances:
        ball_id = instance.ball.id
        if ball_id not in instances_by_ball:
            instances_by_ball[ball_id] = []
        instances_by_ball[ball_id].append(instance)
    
    # Sort instances within each ball type by stats (use worst stats first to preserve better ones)
    for ball_id in instances_by_ball:
        instances_by_ball[ball_id].sort(key=lambda x: x.attack_bonus + x.health_bonus)
    
    instances_to_use = []
    
    # Use individual ingredients first
    recipe_ingredients = await recipe.ingredients.all()
    for ingredient in recipe_ingredients:
        if ingredient.ingredient_id:
            ball_id = ingredient.ingredient_id
            needed = ingredient.quantity
            
            if ball_id in instances_by_ball and len(instances_by_ball[ball_id]) >= needed:
                # Use the required instances
                for i in range(needed):
                    instance = instances_by_ball[ball_id].pop(0)
                    instances_to_use.append(instance.id)
    
    # Handle ingredient groups - use a greedy approach
    recipe_groups = await recipe.ingredient_groups.all()
    for group in recipe_groups:
        group_options = await group.options.all()
        needed = group.required_count
        
        # Sort options by availability (use most abundant first)
        available_options = []
        for option in group_options:
            ball_id = option.ball_id
            available_qty = len(instances_by_ball.get(ball_id, []))
            if available_qty > 0:
                available_options.append((ball_id, available_qty))
        
        available_options.sort(key=lambda x: x[1], reverse=True)
        
        # Use instances from this group
        for ball_id, available_qty in available_options:
            if needed <= 0:
                break
            
            to_use = min(needed, available_qty)
            for i in range(to_use):
                instance = instances_by_ball[ball_id].pop(0)
                instances_to_use.append(instance.id)
            needed -= to_use
        
        # If we couldn't fulfill the group requirement, this shouldn't happen
        if needed > 0:
            return []
    
    return instances_to_use
