from typing import Iterable

from discord import app_commands

from ballsdex.core.merchant_models import GlobalShop, global_shops
from ballsdex.core.utils.transformers import TTLModelTransformer

class GlobalShopTransformer(TTLModelTransformer):
    name = "shop"
    model = GlobalShop()

    def key(self, model: GlobalShop) -> str:
        return model.name

    async def load_items(self) -> Iterable[GlobalShop]:
        return global_shops.values()

GlobalShopTransform = app_commands.Transform[GlobalShop, GlobalShopTransformer]