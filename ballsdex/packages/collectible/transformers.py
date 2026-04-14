from typing import Iterable

from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer
from ballsdex.core.collectible_models import Collectible

class CollectibleTransformer(TTLModelTransformer[Collectible]):
    name = "collectible"
    model = Collectible()

    def key(self, model: Collectible) -> str:
        return model.name

    async def get_from_pk(self, value: int) -> Collectible:
        return await self.model.get(pk=value).prefetch_related("ball", "special")

    async def load_items(self) -> Iterable[Collectible]:
        return await Collectible.all().prefetch_related("ball", "special")

CollectibleTransform = app_commands.Transform[Collectible, CollectibleTransformer]
