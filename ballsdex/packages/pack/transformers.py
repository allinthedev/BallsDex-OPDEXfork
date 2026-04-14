from typing import Iterable

from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer
from ballsdex.core.currency_models import Item

class ItemTransformer(TTLModelTransformer):
    name = "item"
    model = Item()

    def key(self, model: Item) -> str:
        return model.name

    async def load_items(self) -> Iterable[Item]:
        return await Item.all().prefetch_related("special")

ItemTransform = app_commands.Transform[Item, ItemTransformer]
