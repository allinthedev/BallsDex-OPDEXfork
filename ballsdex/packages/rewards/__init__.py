from ballsdex.packages.rewards.cog import Rewards

async def setup(bot):
    await bot.add_cog(Rewards(bot)) 