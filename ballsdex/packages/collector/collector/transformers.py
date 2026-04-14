from datetime import datetime
from typing import Iterable

from discord import app_commands

from ballsdex.core.utils.transformers import TTLModelTransformer
from tortoise.timezone import now as tortoise_now, get_default_timezone

from ballsdex.core.collector_models import Collector

class CollectorTransformer(TTLModelTransformer[Collector]):
    name = "collector"
    model = Collector()

    def key(self, model: Collector) -> str:
        return model.name

    async def get_from_pk(self, value: int) -> Collector:
        return await self.model.get(pk=value).prefetch_related("requirements")

class CollectorEnabledTransformer(CollectorTransformer):
    async def load_items(self) -> Iterable[Collector]:
        return [
            x
            for x in await Collector.all()
            if (x.start_date or datetime.min.replace(tzinfo=get_default_timezone()))
            <= tortoise_now()
            <= (x.end_date or datetime.max.replace(tzinfo=get_default_timezone()))
        ]

CollectorTransform = app_commands.Transform[Collector, CollectorTransformer]
CollectorEnabledTransform = app_commands.Transform[Collector, CollectorEnabledTransformer]