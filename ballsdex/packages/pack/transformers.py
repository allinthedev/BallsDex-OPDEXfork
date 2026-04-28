from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer
from ballsdex.core.currency_models import Item

class ItemTransformer(TTLModelTransformer[Item]):
    name = "item"
    model = Item()

    def key(self, model: Item) -> str:
        return model.name

    async def get_from_pk(self, value: int) -> Item:
        return await self.model.get(pk=value).prefetch_related("special", "balls")

ItemTransform = app_commands.Transform[Item, ItemTransformer]
