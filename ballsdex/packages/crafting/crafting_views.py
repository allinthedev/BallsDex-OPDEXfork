import discord
import random
from .models import CraftingRecipe
from .models import CraftingIngredient
from .models import CraftingIngredientGroup
from .models import CraftingGroupOption

from .logic import (
    find_matching_recipes, 
    determine_ingredient_usage,
    can_craft_recipe
)


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
from ballsdex.settings import settings 
from .session_manager import crafting_sessions 

class CraftingView(discord.ui.View):
    def __init__(self, bot, player, session_data):
        super().__init__(timeout=600)  # 10 minute timeout
        self.bot = bot
        self.player = player
        self.session_data = session_data
        self.authorized_user_id = player.discord_id  
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user is authorized to interact with this view"""
        if interaction.user.id != self.authorized_user_id:
            await interaction.response.send_message(
                "❌ Only the person who started this crafting session can use these buttons!",
                ephemeral=True
            )
            return False
        return True
    
    @discord.ui.button(label="🔨 Craft", style=discord.ButtonStyle.success)
    async def craft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if current ingredients match any recipe
        possible_recipes = await find_matching_recipes(self.session_data['ingredient_instances'])
        
        if len(self.session_data['ingredient_instances']) == 0:
            await interaction.response.send_message("You haven't added any ingredients yet!", ephemeral=True)
            return
            
        if not possible_recipes:
            await interaction.response.send_message(
                "Your current ingredients don't match any known recipes!", 
                ephemeral=True
            )
            return
        
        # If multiple recipes match, let user choose
        if len(possible_recipes) > 1:
            await self.show_recipe_selection(interaction, possible_recipes)
        else:
            await self.execute_craft(interaction, possible_recipes[0])
        self.stop() 
        
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in crafting_sessions:
            del crafting_sessions[user_id]
        
        embed = discord.Embed(
            title="Crafting Cancelled",
            description="Your crafting session has been cancelled. All ingredients have been returned.",
            color=0xff0000
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop() 
        
    async def on_timeout(self):
        user_id = self.player.discord_id
        crafting_sessions.pop(user_id, None)
    
        try:
            # Check if message exists and is still valid
            if self.session_data.get("message"):
                await self.session_data["message"].edit(
                    embed=discord.Embed(
                        title="Crafting Timed Out",
                        description="Your crafting session expired after 10 minutes of inactivity.",
                        color=0x808080
                    ),
                    view=None
                )
        except (discord.HTTPException, discord.NotFound, discord.Forbidden):
            pass
            
    async def show_recipe_selection(self, interaction, possible_recipes):
        embed = discord.Embed(
            title="Multiple Recipes Available!",
            description="Your ingredients can craft multiple items. Choose which one:",
            color=0x00ff00
        )
        
        options = []
        for i, recipe in enumerate(possible_recipes):
            emoji = self.bot.get_emoji(recipe.result.emoji_id)
            special_prefix = f"{self.session_data['special'].emoji} " if self.session_data.get('special') else ""
            options.append(discord.SelectOption(
                label=f"{special_prefix}{recipe.result.country}",
                description=f"Craft {special_prefix}{recipe.result.country}",
                value=str(i),
                emoji=emoji
            ))
        
        select = RecipeSelect(options, possible_recipes, self, self.authorized_user_id)
        view = discord.ui.View()
        view.add_item(select)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def execute_craft(self, interaction, recipe):
        try:
            # Determine which ingredients to use (including group selections)
            ingredients_to_use = await determine_ingredient_usage(
                recipe,
                self.session_data['ingredient_instances']
            )
    
            if not ingredients_to_use:
                await interaction.response.send_message(
                    "Unable to determine ingredient usage. This shouldn't happen!",
                    ephemeral=True
                )
                return
    
            # Get the actual ball instances to use
            ball_instances_to_delete = []
            for instance_id in ingredients_to_use:
                instance = await BallInstance.get(id=instance_id)
                await instance.fetch_related('ball', 'special')
                ball_instances_to_delete.append(instance)
    
            # Clean up - first remove any lingering trade references, then delete instances
            instance_ids_to_delete = [ball.id for ball in ball_instances_to_delete]
    
            try:
                # Remove any trade object references that might be lingering
                await TradeObject.filter(ballinstance_id__in=instance_ids_to_delete).delete()
                print(f"Cleaned up trade object references for: {instance_ids_to_delete}")
            except Exception as e:
                print(f"Error cleaning up trade objects: {e}")
                del crafting_sessions[interaction.user.id]
                await interaction.followup.send(
                    "Error cleaning up trade references. Crafting session ended for security.",
                    ephemeral=True
                )
                return
    
            try:
                deleted_count = await BallInstance.filter(id__in=instance_ids_to_delete).delete()    
                if deleted_count != len(instance_ids_to_delete):
                    print(f"🚨 Mismatch in deletion count: expected {len(instance_ids_to_delete)} but got {deleted_count}")
                    del crafting_sessions[interaction.user.id]
                    await interaction.followup.send(
                        "Not all ingredients were properly consumed. Crafting session ended for security.",
                        ephemeral=True
                    )
                    return
    
            except Exception as e:
                print(f"Error deleting ball instances: {e}")
                del crafting_sessions[interaction.user.id]
                await interaction.followup.send(
                    "Error consuming ingredients. Crafting session ended for security.",
                    ephemeral=True
                )
                return
    
            # Create the new ball
            await recipe.fetch_related("result")
            crafted_instance = await BallInstance.create(
                player=self.player,
                ball=recipe.result,
                special=self.session_data.get('special'),
                health_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
            )
    
            # Calculate stats
            total_sacrificed_attack = sum(ball.attack_bonus for ball in ball_instances_to_delete)
            total_sacrificed_health = sum(ball.health_bonus for ball in ball_instances_to_delete)
    
            # Create success embed
            ball_emoji = self.bot.get_emoji(recipe.result.emoji_id)
            special_prefix = (
                f"{self.session_data['special'].emoji} {self.session_data['special'].name} "
                if self.session_data.get('special') else ""
            )
            name = f"{special_prefix}{ball_emoji} {recipe.result.country}"
    
            embed = discord.Embed(
                title="✅ Crafting Successful!",
                description=f"Successfully crafted **{name}** (ID: #{crafted_instance.pk:0X})!",
                color=0x00ff00
            )
            embed.add_field(
                name="New instance Stats",
                value=f"**ATK:** {crafted_instance.attack_bonus:+d} | **HP:** {crafted_instance.health_bonus:+d}",
                inline=False
            )
    
            # Show ingredients used
            used_summary = []
            for ball in ball_instances_to_delete:
                ball_emoji = self.bot.get_emoji(ball.ball.emoji_id)
                special_text = f"{ball.special.emoji} " if ball.special else ""
                used_summary.append(f"{ball_emoji} {special_text}{ball.ball.country} (#{ball.pk:0X})")
    
            embed.add_field(
                name="Ingredients Used",
                value="\n".join(used_summary),
                inline=False
            )
    
            embed.add_field(
                name="Total Stats of instances used for crafting",
                value=f"**ATK:** {total_sacrificed_attack:+d} | **HP:** {total_sacrificed_health:+d}",
                inline=False
            )
    
            net_attack = crafted_instance.attack_bonus - total_sacrificed_attack
            net_health = crafted_instance.health_bonus - total_sacrificed_health
            if net_attack != 0 or net_health != 0:
                embed.add_field(
                    name="Net Change",
                    value=f"**ATK:** {net_attack:+d} | **HP:** {net_health:+d}",
                    inline=False
                )
    
            await interaction.response.edit_message(embed=embed, view=None)
    
            # Update session memory
            for instance_id in ingredients_to_use:
                if instance_id in self.session_data['ingredient_instances']:
                    self.session_data['ingredient_instances'].remove(instance_id)
    
            if not self.session_data['ingredient_instances']:
                del crafting_sessions[interaction.user.id]
    
        except Exception as e:
            print(f"Unexpected error in execute_craft: {e}")
            await interaction.response.send_message(
                "An unexpected error occurred during crafting. Please try again.",
                ephemeral=True
            )
            if interaction.user.id in crafting_sessions:
                del crafting_sessions[interaction.user.id]         

class RecipeSelect(discord.ui.Select):
    def __init__(self, options, recipes, parent_view, authorized_user_id):
        super().__init__(placeholder="Choose which item to craft...", options=options)
        self.recipes = recipes
        self.parent_view = parent_view
        self.authorized_user_id = authorized_user_id
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the user is authorized to interact with this select menu"""
        if interaction.user.id != self.authorized_user_id:
            await interaction.response.send_message(
                "❌ Only the person who started this crafting session can use this menu!",
                ephemeral=True
            )
            return False
        return True
    
    async def callback(self, interaction):
        recipe_index = int(self.values[0])
        selected_recipe = self.recipes[recipe_index]
        await self.parent_view.execute_craft(interaction, selected_recipe)
