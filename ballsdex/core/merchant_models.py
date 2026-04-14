from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from tortoise import models, fields
from tortoise.timezone import now as tortoise_now, get_default_timezone

from ballsdex.core.models import balls, specials

if TYPE_CHECKING:
    from ballsdex.core.models import Ball, Player, Special

merchant_items: dict[int, MerchantItem] = {}
global_shops: dict[int, GlobalShop] = {}

class MerchantSettings(models.Model):
    rotation = fields.BigIntField(description="Duration of the items in minutes. Default to 24 hours.", default=1440)
    items = fields.BigIntField(description="How many items will be in the store. Default to 3 items.", default=3)

    @classmethod
    async def load(cls):
        obj, _ = await cls.get_or_create(pk=1)
        return obj

    @property
    def rotation_delta(self) -> timedelta:
        return timedelta(minutes=self.rotation)

    def __str__(self) -> str:
        return "Merchant Settings"


class MerchantItem(models.Model):
    name = fields.CharField(unique=True, max_length=64)
    prize = fields.IntField(null=True)
    start_date = fields.DatetimeField(
        description="Start time of the item. If blank, starts immediately",
        null=True,
        default=None
    )
    end_date = fields.DatetimeField(
        description="End time of the item. If blank, the item is permanent",
        null=True,
        default=None
    )
    rarity = fields.FloatField(description="Value between 0 and 1, determine if a item is rarest than other")
    ball: fields.ForeignKeyRelation["Ball"] = fields.ForeignKeyField(
        "models.Ball",
        on_delete=fields.CASCADE
    )
    ball_id: int
    special: fields.ForeignKeyNullableRelation["Special"] = fields.ForeignKeyField(
        "models.Special",
        on_delete=fields.SET_NULL,
        null=True,
        default=None
    )
    special_id: int | None
    created_at = fields.DatetimeField(auto_now_add=True)

    @property
    def cached_ball(self) -> "Ball":
        return balls.get(self.ball_id, self.ball)

    @property
    def cached_special(self) -> "Special | None":
        return specials.get(self.special_id, self.special) if self.special_id else None

    @property
    def enabled(self) -> bool:
        """
        Checks if this item is active.
        """
        return (
            (self.start_date or datetime.min.replace(tzinfo=get_default_timezone()))
            <= tortoise_now()
            <= (self.end_date or datetime.max.replace(tzinfo=get_default_timezone()))
        )

    def __str__(self):
        return self.name


class MerchantInstance(models.Model):
    player: fields.OneToOneRelation["Player"] = fields.OneToOneField(
        "models.Player",
        on_delete=fields.CASCADE,
        related_name="merchant"
    )
    items: fields.ManyToManyRelation[MerchantItem] = fields.ManyToManyField(
        "models.MerchantItem",
        through="merchantinstance_items"
    )
    rotation_ends_at = fields.DatetimeField()

    @property
    def rotation_expired(self) -> bool:
        """
        Check if the rotation has ended.
        """
        return self.rotation_ends_at <= tortoise_now()


class GlobalShop(models.Model):
    name = fields.CharField(max_length=64, unique=True)
    banner = fields.CharField(max_length=200, description="An optional promotional banner for this shop.")
    items: fields.ManyToManyRelation[MerchantItem] = fields.ManyToManyField(
        "models.MerchantItem",
        through="globalshop_items"
    )
