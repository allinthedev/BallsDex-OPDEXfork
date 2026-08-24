from typing import TYPE_CHECKING

from .cog import AuctionHouse
from .treasures_cog import TreasureSale

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(AuctionHouse(bot))
    await bot.add_cog(TreasureSale(bot))
