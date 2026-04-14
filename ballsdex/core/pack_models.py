from datetime import timedelta
from typing import TYPE_CHECKING
from tortoise import models, fields, timezone

if TYPE_CHECKING:
    from .models import Player

class PackResource(models.Model):
    player: fields.OneToOneRelation["Player"] = fields.OneToOneField(
        "models.Player", 
        on_delete=fields.CASCADE, 
        related_name="pack_resource"
    )
    uses = fields.IntField(default=0)
    daily_cooldown = fields.DatetimeField(null=True)
    weekly_cooldown = fields.DatetimeField(null=True)

    async def set_daily_cooldown(self):
        self.daily_cooldown = timezone.now()
        await self.save(update_fields=("daily_cooldown",))
    
    async def set_weekly_cooldown(self):
        self.weekly_cooldown = timezone.now()
        await self.save(update_fields=("weekly_cooldown",))
    
    async def remove_daily_cooldown(self):
        self.daily_cooldown = None
        self.uses = 0
        await self.save(update_fields=("daily_cooldown", "uses"))
    
    async def remove_weekly_cooldown(self):
        self.weekly_cooldown = None
        await self.save(update_fields=("weekly_cooldown",))

    async def is_daily_on_cooldown(self) -> bool:
        await self.refresh_from_db(fields=("daily_cooldown",))
        self.daily_cooldown
        return self.daily_cooldown is not None and (self.daily_cooldown + timedelta(days=1)) > timezone.now()

    async def is_weekly_on_cooldown(self) -> bool:
        await self.refresh_from_db(fields=("weekly_cooldown",))
        self.weekly_cooldown
        return self.weekly_cooldown is not None and (self.weekly_cooldown + timedelta(weeks=1)) > timezone.now()