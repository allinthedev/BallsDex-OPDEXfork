import logging
from typing import TYPE_CHECKING

from .cog import Merchant

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger(__name__)

async def setup(bot: "BallsDexBot"):
    from ballsdex.core.merchant_models import MerchantItem, GlobalShop, merchant_items, global_shops

    merchant_items.clear()
    for item in await MerchantItem.all():
        merchant_items[item.pk] = item

    global_shops.clear()
    for shop in await GlobalShop.all():
        global_shops[shop.pk] = shop

    log.info(f"Cached {len(merchant_items)} items and {len(global_shops)} shops.")
    await bot.add_cog(Merchant(bot))
