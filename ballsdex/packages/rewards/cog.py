from typing import Optional, List, Dict, Any
import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os

from ballsdex.core.models import BallInstance, Player as PlayerModel, Ball, Economy, Regime, Special
from ballsdex.core.utils.enums import SortingChoices
from ballsdex.core.utils.transformers import BallEnabledTransform, SpecialTransform
from ballsdex.packages.trade.menu import ConfirmView
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.packages.countryballs.countryball import BallSpawnView
from ballsdex.settings import settings
from ballsdex.core.utils.buttons import ConfirmChoiceView

PENDING_REWARDS_FILE = os.path.join(os.path.dirname(__file__), "pending_rewards.json")
OPT_OUT_FILE = os.path.join(os.path.dirname(__file__), "opt_out.json")

class PendingReward:
    def __init__(self, user_id: int, reward_info: Dict[str, Any], expiry_time: datetime):
        self.user_id = user_id
        self.reward_info = reward_info
        self.expiry_time = expiry_time

class RewardClaimView(discord.ui.View):
    def __init__(self, reward_manager, user_id: int, reward_info: Dict[str, Any], expiry_time: datetime):
        super().__init__(timeout=None)
        self.reward_manager = reward_manager
        self.user_id = user_id
        self.reward_info = reward_info
        self.expiry_time = expiry_time
        self.message = None
        self.claimed = False

    @discord.ui.button(label="Claim Reward", style=discord.ButtonStyle.green)
    async def claim_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your reward!", ephemeral=True)
            return

        if self.claimed:
            await interaction.response.send_message("You have already claimed this reward!", ephemeral=True)
            return

        if interaction.user.id in self.reward_manager.bot.blacklist:
            await interaction.response.send_message("Blacklisted users cannot claim rewards.", ephemeral=True)
            return

        if datetime.now() > self.expiry_time:
            embed = discord.Embed(
                title="⏰ Reward Expired",
                description=f"This reward has exceeded the 24-hour claim period!\n"
                           f"Reward Type: {self.reward_info['type']}\n"
                           f"Reward Content: {self.reward_info['description']}",
                color=discord.Color.red()
            )
            try:
                await interaction.message.edit(embed=embed, view=None)
            except:
                pass
            await interaction.response.send_message("This reward has expired!", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            try:
                player = await PlayerModel.get(discord_id=interaction.user.id)
            except Exception as e:
                print(f"Error getting player data: {str(e)}")
                await interaction.followup.send("Unable to get player data. Please ensure you have started the game!", ephemeral=True)
                return
            
            try:
                balls_info = []
                for _ in range(self.reward_info.get('reward_count', 1)):
                    if self.reward_info.get("specific_balls"):
                        ball_id = random.choice(self.reward_info["specific_balls"])
                        ball = await Ball.get(id=ball_id)
                    elif self.reward_info.get("rarity_range"):
                        min_rarity, max_rarity = self.reward_info["rarity_range"]
                        available_balls = await Ball.filter(enabled=True).all()
                        filtered_balls = [
                            ball for ball in available_balls 
                            if min_rarity <= ball.rarity <= max_rarity
                        ]
                        
                        if not filtered_balls:
                            filtered_balls = available_balls
                        
                        ball = random.choices(
                            population=filtered_balls,
                            weights=[float(b.rarity) for b in filtered_balls],
                            k=1
                        )[0]
                    else:
                        available_balls = await Ball.filter(enabled=True).all()
                        ball = random.choices(
                            population=available_balls,
                            weights=[float(b.rarity) for b in available_balls],
                            k=1
                        )[0]
                    
                    special = None
                    if self.reward_info.get("special_event"):
                        try:
                            special = await Special.get(id=int(self.reward_info["special_event"]))
                        except Exception as e:
                            print(f"Error getting special event: {str(e)}")
                    
                    spawn_view = BallSpawnView(self.reward_manager.bot, ball)
                    spawn_view.special = special
                    instance = await BallInstance.create(
                        ball=ball,
                        player=player,
                        special=special,
                        attack_bonus=random.randint(-settings.max_attack_bonus, settings.max_attack_bonus),
                        health_bonus=random.randint(-settings.max_health_bonus, settings.max_health_bonus),
                    )
                    emoji = ""
                    if special and getattr(special, "emoji", None):
                        emoji = f"{special.emoji} "
                    balls_info.append(f"{emoji}{ball.country} (ATK:{instance.attack} HP:{instance.health})")
            except Exception as e:
                print(f"Error generating ball: {str(e)}")
                await interaction.followup.send("Error generating reward ball. Please try again later!", ephemeral=True)
                return
            
            self.claimed = True
            try:
                if interaction.user.id in self.reward_manager.pending_rewards:
                    del self.reward_manager.pending_rewards[interaction.user.id]
                    self.reward_manager.save_pending_rewards()
            except Exception as e:
                print(f"Error removing pending reward: {str(e)}")
            try:
                embed = discord.Embed(
                    title="✅ Reward Claimed",
                    description=f"You have successfully claimed your reward!\n"
                               f"Reward Type: {self.reward_info['type']}\n"
                               f"Reward Content: {self.reward_info['description']}\n"
                               f"You received:\n" + "\n".join(balls_info),
                    color=discord.Color.green()
                )
                await interaction.message.edit(embed=embed, view=None)
            except Exception as e:
                print(f"Error updating message content: {str(e)}")
            try:
                await interaction.followup.send(
                    f"🎉 Congratulations on receiving your reward!\nYou received:\n" + "\n".join(balls_info)
                )
            except Exception as e:
                print(f"Error sending reward message: {str(e)}")
        except Exception as e:
            print(f"Unexpected error while distributing reward: {str(e)}")
            await interaction.followup.send("Error occurred while distributing reward. Please try again later! If the problem persists, contact an administrator.", ephemeral=True)

    @discord.ui.button(label="Opt out of rewards", style=discord.ButtonStyle.danger)
    async def decline_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your reward!", ephemeral=True)
            return
        if self.claimed:
            await interaction.response.send_message("You have already claimed this reward!", ephemeral=True)
            return
        view = ConfirmChoiceView(
            interaction,
            accept_message="You have opted out of the rewards service. You will no longer receive any reward notifications.",
            cancel_message="Opt-out operation cancelled."
        )
        await interaction.response.send_message(
            "Are you sure you want to opt out of the rewards service?\n"
            "⚠️ Note: After opting out, you will no longer receive any reward notifications!\n"
            "This operation can only be reverted by contacting an administrator!",
            view=view,
            ephemeral=True
        )
        await view.wait()
        if view.value:

            self.reward_manager.add_to_opt_out(interaction.user.id)

            try:
                if interaction.user.id in self.reward_manager.pending_rewards:
                    del self.reward_manager.pending_rewards[interaction.user.id]
                    self.reward_manager.save_pending_rewards()
            except Exception as e:
                print(f"Error removing pending reward: {str(e)}")

            for item in self.children:
                item.disabled = True

            try:
                embed = discord.Embed(
                    title="❌ You have opted out of the rewards service",
                    description="You have chosen not to receive any further reward notifications.",
                    color=discord.Color.red()
                )
                await interaction.message.edit(embed=embed, view=self)
            except Exception as e:
                print(f"Error updating message content: {str(e)}")

    async def on_timeout(self):
        if not self.claimed:
            embed = discord.Embed(
                title="⏰ Reward Expired",
                description=f"This reward has exceeded the 24-hour claim period!\n"
                           f"Reward Type: {self.reward_info['type']}\n"
                           f"Reward Content: {self.reward_info['description']}",
                color=discord.Color.red()
            )
            try:
                await self.message.edit(embed=embed, view=None)
            except:
                pass

class RewardManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        rewards_dir = os.path.dirname(PENDING_REWARDS_FILE)
        if not os.path.exists(rewards_dir):
            os.makedirs(rewards_dir)
        self.pending_rewards = self.load_pending_rewards()
        self.confirmation_timeout = 86400
        self.opt_out_users = self.load_opt_out()

    def load_pending_rewards(self):
        if os.path.exists(PENDING_REWARDS_FILE):
            with open(PENDING_REWARDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = {}
            for uid, info in data.items():
                result[int(uid)] = PendingReward(
                    int(uid),
                    info["reward_info"],
                    datetime.fromisoformat(info["expiry_time"])
                )
            return result
        return {}

    def save_pending_rewards(self):
        data = {}
        for uid, reward in self.pending_rewards.items():
            data[str(uid)] = {
                "reward_info": reward.reward_info,
                "expiry_time": reward.expiry_time.isoformat()
            }
        with open(PENDING_REWARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_opt_out(self):
        """Load opt-out user list"""
        if os.path.exists(OPT_OUT_FILE):
            with open(OPT_OUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("opt_out_users", [])
        return []

    def save_opt_out(self):
        """Save opt-out user list"""
        data = {"opt_out_users": self.opt_out_users}
        with open(OPT_OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_to_opt_out(self, user_id: int):
        """Add user to opt-out list"""
        if user_id not in self.opt_out_users:
            self.opt_out_users.append(user_id)
            self.save_opt_out()

    def is_opt_out(self, user_id: int) -> bool:
        """Check if user has opted out of rewards service"""
        return user_id in self.opt_out_users

    async def send_reward_confirmation(self, interaction: discord.Interaction, user: discord.User, reward_info: Dict[str, Any]) -> bool:
        try:

            if user.id in self.bot.blacklist:
                return False

            if self.is_opt_out(user.id):
                return False
            expiry_time = datetime.now() + timedelta(seconds=self.confirmation_timeout)
            view = RewardClaimView(self, user.id, reward_info, expiry_time)
            embed = discord.Embed(
                title="🎁 New Reward Notification",
                description=f"You have a new reward to claim!\n"
                           f"Reward Type: {reward_info['type']}\n"
                           f"Reward Content: {reward_info['description']}\n"
                           f"Please click the button below to claim your reward within 24 hours.",
                color=discord.Color.blue()
            )
            message = await user.send(embed=embed, view=view)
            
            self.pending_rewards[user.id] = PendingReward(user.id, reward_info, expiry_time)
            self.save_pending_rewards()
            
            view.message = message
            
            return True
        except discord.Forbidden:
            await interaction.channel.send(f'⚠️ | Could not distribute rewards to {user.id} {user.name} as they have their DM closed')
            return False
        except Exception as e:
            await interaction.channel.send(f"Error occurred while distributing reward: {str(e)}")
            return False

    async def check_pending_reward(self, user_id: int) -> Optional[Dict[str, Any]]:
        if user_id not in self.pending_rewards:
            return None
            
        reward = self.pending_rewards[user_id]
        if datetime.now() > reward.expiry_time:
            del self.pending_rewards[user_id]
            self.save_pending_rewards()
            return None
            
        return reward.reward_info
            
    async def distribute_rewards(
        self,
        bot: commands.Bot,
        reward_type: str,
        reward_description: str,
        rarity_range: Optional[tuple] = None,
        specific_balls: Optional[List[Ball]] = None,
        target_users: Optional[List[discord.User]] = None,
        reward_count: int = 1,
        interaction: Optional[discord.Interaction] = None,
        special_event: Optional[SpecialTransform] = None
    ) -> Dict[str, Any]:
        results = {
            "total_users": 0,
            "notified_users": 0,
            "failed_users": 0,
            "opt_out_users": 0,
            "blacklisted_users": 0
        }
        progress_message = None
        batch_size = 10
        if not target_users:
            bot_id = bot.user.id
            players = await PlayerModel.all()
            target_users = []
            for player in players:
                if player.discord_id == bot_id:
                    continue
                user = bot.get_user(player.discord_id)
                if not user:
                    try:
                        user = await bot.fetch_user(player.discord_id)
                    except Exception:
                        user = None
                if user and not user.bot:
                    target_users.append(user)
        results["total_users"] = len(target_users)
        total = len(target_users)
        notified = 0
        failed = 0
        opt_out = 0
        blacklisted = 0
        progress_message = await interaction.followup.send(f":gift: Distributing rewards...\nNotified: 0\nFailed: 0\nOpted-out users: 0\nBlacklisted users: 0\nRemaining: {total}", ephemeral=True)
        for i in range(0, total, batch_size):
            batch = target_users[i:i+batch_size]
            tasks = [self.send_reward_confirmation(interaction, user, {
                "type": reward_type,
                "description": reward_description,
                "rarity_range": rarity_range,
                "specific_balls": [b.id for b in specific_balls] if specific_balls else None,
                "reward_count": reward_count,
                "special_event": special_event.id if special_event else None
            }) for user in batch]
            results_list = []
            for task in tasks:
                try:
                    result = await task
                    results_list.append(result)
                except Exception as e:
                    print(f"Error distributing reward: {str(e)}")
                    results_list.append(False)
            for idx, user in enumerate(batch):
                if user.id in self.bot.blacklist:
                    blacklisted += 1
                elif self.is_opt_out(user.id):
                    opt_out += 1
                elif results_list[idx]:
                    notified += 1
                else:
                    failed += 1
            await progress_message.edit(
                content=f":gift: Distributing rewards...\nNotified: {notified}\nFailed: {failed}\nOpted-out users: {opt_out}\nBlacklisted users: {blacklisted}\nRemaining: {max(0, total - (i+batch_size))}"
            )
            await asyncio.sleep(1)
        results["notified_users"] = notified
        results["failed_users"] = failed
        results["opt_out_users"] = opt_out
        results["blacklisted_users"] = blacklisted
        return results

class Rewards(commands.GroupCog, group_name="rewards"):
    """
    Reward system related commands.
    """
    hidden = True
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reward_manager = RewardManager(bot)
        self.bot.loop.create_task(self.check_reward_removal())
        
    async def check_reward_removal(self):
        pending_rewards_copy = dict(self.reward_manager.pending_rewards)
        expired_rewards = []
        
        for user_id, reward in pending_rewards_copy.items():
            if datetime.now() > reward.expiry_time:
                expired_rewards.append(user_id)
                continue
                
        for user_id in expired_rewards:
            if user_id in self.reward_manager.pending_rewards:
                del self.reward_manager.pending_rewards[user_id]
                
        self.reward_manager.save_pending_rewards()
        
    async def economy_type_autocomplete(self, interaction: discord.Interaction, current: str):
        economies = await Economy.all()
        return [
            discord.app_commands.Choice(name=e.name, value=e.name)
            for e in economies if current.lower() in e.name.lower()
        ][:25]

    async def regime_type_autocomplete(self, interaction: discord.Interaction, current: str):
        regimes = await Regime.all()
        return [
            discord.app_commands.Choice(name=r.name, value=r.name)
            for r in regimes if current.lower() in r.name.lower()
        ][:25]

    async def special_event_autocomplete(self, interaction: discord.Interaction, current: str):
        specials = await Special.filter(hidden=False)
        return [
            discord.app_commands.Choice(name=s.name, value=str(s.id))
            for s in specials if current.lower() in s.name.lower()
        ][:25]

    async def ball_autocomplete(self, interaction: discord.Interaction, current: str):
        balls = await Ball.filter(enabled=True)
        return [
            discord.app_commands.Choice(name=ball.country, value=ball.country)
            for ball in balls if current.lower() in ball.country.lower()
        ][:25]

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids)
    async def distribute(
        self,
        interaction: discord.Interaction,
        reward_type: str,
        reward_description: str,
        reward_count: int = 1,
        economy_type: Optional[str] = None,
        regime_type: Optional[str] = None,
        specific_ball: Optional[str] = None,
        min_rarity: Optional[int] = None,
        max_rarity: Optional[int] = None,
        target_role: Optional[discord.Role] = None,
        target_user_ids: Optional[str] = None,
        special_event: Optional[SpecialTransform] = None
    ):
        """
        Distribute rewards to specified users.

        Parameters
        ----------
        reward_type: str
            Type of reward
        reward_description: str
            Description of reward
        reward_count: int
            Number of rewards per user
        economy_type: Optional[str]
            Economy type (auto-fetches all economy names)
        regime_type: Optional[str]
            Regime type (auto-fetches all regime names)
        specific_ball: Optional[str]
            Specific ball type (auto-fetches all ball names)
        min_rarity: Optional[int]
            Minimum rarity
        max_rarity: Optional[int]
            Maximum rarity
        target_role: Optional[discord.Role]
            Target role (if specified, only sends to users with this role)
        target_user_ids: Optional[str]
            Target user IDs (can input multiple IDs, separated by commas or spaces, takes priority over target_role)
        special_event: Optional[SpecialTransform]
            Special event (if specified, reward balls will have special event background)
        """
        await interaction.response.defer(thinking=True)
        
        if reward_count < 1:
            await interaction.followup.send("Reward count must be greater than 0!", ephemeral=True)
            return
        if reward_count > 10:
            await interaction.followup.send("Maximum 10 rewards can be distributed at once!", ephemeral=True)
            return
            
        rarity_range = None
        if (min_rarity is not None and max_rarity is None) or (min_rarity is None and max_rarity is not None):
            await interaction.followup.send("Please fill in both minimum and maximum rarity!", ephemeral=True)
            return
        if min_rarity is not None and max_rarity is not None:
            if min_rarity > max_rarity:
                await interaction.followup.send("Minimum rarity cannot be greater than maximum rarity!", ephemeral=True)
                return
            rarity_range = (min_rarity, max_rarity)
            
        target_users = None
        if target_user_ids:
            id_list = [i.strip() for i in target_user_ids.replace(',', ' ').split() if i.strip().isdigit()]
            if not id_list:
                await interaction.followup.send("Please enter valid user IDs!", ephemeral=True)
                return
            target_users = []
            for uid in id_list:
                try:
                    user = self.bot.get_user(int(uid))
                    if not user:
                        user = await self.bot.fetch_user(int(uid))
                    if user:
                        target_users.append(user)
                except Exception:
                    continue
            if not target_users:
                await interaction.followup.send("No valid user IDs found!", ephemeral=True)
                return
        elif target_role:
            target_users = target_role.members
            
        has_type_filter = specific_ball or economy_type or regime_type
        
        available_balls = None
        
        if has_type_filter:
            query = Ball.filter(enabled=True)
            
            if specific_ball:
                query = query.filter(country=specific_ball)
            if economy_type:
                query = query.filter(economy__name=economy_type)
            if regime_type:
                query = query.filter(regime__name=regime_type)
                
            if rarity_range:
                min_r, max_r = rarity_range
                query = query.filter(rarity__gte=min_r, rarity__lte=max_r)
                
            available_balls = await query.all()
            
            if not available_balls:
                conditions = []
                if specific_ball: conditions.append(f"Ball: {specific_ball}")
                if economy_type: conditions.append(f"Economy: {economy_type}")
                if regime_type: conditions.append(f"Regime: {regime_type}")
                if rarity_range:
                    conditions.append(f"Rarity: {rarity_range[0]}~{rarity_range[1]}")
                
                await interaction.followup.send(
                    f"No balls found matching all conditions:\n" + "\n".join(conditions), 
                    ephemeral=True
                )
                return
                
        from ballsdex.core.utils.logging import log_action
        log_msg = (
            f"[Reward Distribution] Admin {interaction.user} ({interaction.user.id}) used /rewards distribute command\n"
            f"Type: {reward_type}\nDescription: {reward_description}\nCount: {reward_count}\n"
            f"Economy Type: {economy_type or '-'}\nRegime Type: {regime_type or '-'}\nSpecific Ball: {specific_ball or '-'}\n"
            f"Rarity Range: {min_rarity or '-'}~{max_rarity or '-'}\nTarget Role: {getattr(target_role, 'name', '-') if target_role else '-'}\n"
            f"Target User IDs: {target_user_ids or '-'}\nSpecial Event: {getattr(special_event, 'id', '-') if special_event else '-'}"
        )
        await log_action(log_msg, self.bot)
        
        results = await self.reward_manager.distribute_rewards(
            self.bot,
            reward_type,
            reward_description,
            rarity_range=rarity_range,
            specific_balls=available_balls,
            target_users=target_users,
            reward_count=reward_count,
            interaction=interaction,
            special_event=special_event
        )
        
        await interaction.followup.send(
            f"🎁 Reward distribution completed!\n"
            f"Total users: {results['total_users']}\n"
            f"Notified: {results['notified_users']}\n"
            f"Failed: {results['failed_users']}\n"
            f"Opted-out users: {results['opt_out_users']}\n"
            f"Blacklisted users: {results['blacklisted_users']}\n"
            f"Rewards per user: {reward_count}"
        )

    distribute.autocomplete("economy_type")(economy_type_autocomplete)
    distribute.autocomplete("regime_type")(regime_type_autocomplete)
    distribute.autocomplete("special_event")(special_event_autocomplete)
    distribute.autocomplete("specific_ball")(ball_autocomplete) 
