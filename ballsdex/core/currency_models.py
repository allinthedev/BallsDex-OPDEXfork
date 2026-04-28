from tortoise import models, fields
from .models import Ball, Player, Special, balls

class Item(models.Model):
    name = fields.CharField(max_length=64)
    description = fields.TextField(null=True, description="An optional description for the item")
    prize = fields.BigIntField(null=True, description="The prize of the item. If blanks, it will free")
    emoji_id = fields.BigIntField(null=True, default=None)
    minimum_rarity = fields.FloatField(description="Minimum rarity range.", null=True)
    maximum_rarity = fields.FloatField(description="Maximum rarity range.", null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    special: fields.ForeignKeyNullableRelation[Special] = fields.ForeignKeyField(
        "models.Special",
        on_delete=fields.SET_NULL,
        null=True,
        default=None,
        description="The special of the item (optional)"
    )
    balls: fields.BackwardFKRelation["ItemBall"]

    def __str__(self) -> str:
        return self.name


class ItemBall(models.Model):
    item: fields.ForeignKeyRelation[Item] = fields.ForeignKeyField(
        "models.Item",
        on_delete=fields.CASCADE,
        related_name="balls"
    )
    ball: fields.ForeignKeyRelation[Ball] = fields.ForeignKeyField(
        "models.Ball",
        on_delete=fields.CASCADE,
    )
    ball_id: int

    @property
    def cached_ball(self) -> Ball:
        return balls.get(self.ball_id, self.ball)


class CurrencySettings(models.Model):
    name = fields.CharField(max_length=64)
    plural_name = fields.CharField(max_length=64)
    emoji_id = fields.BigIntField(description="Emoji id of the currency", null=True)
    spawn_chance = fields.FloatField(default=0.2, description="Value between 0 and 1, chances to spawn currency.")
    spawn_amount = fields.IntField(default=500, description="The amount of currency to give from a spawn.")

    @classmethod
    async def load(cls):
        obj, _ = await cls.get_or_create(
            pk=1,
            defaults={
                "name": "Coin",
                "plural_name": "Coins",
            }
        )
        return obj

    def display_name(self, amount: int) -> str:
        return self.name if amount == 1 else self.plural_name

    def __str__(self) -> str:
        return self.name

class MoneyInstance(models.Model):
    player: fields.OneToOneRelation[Player] = fields.OneToOneField(
        "models.Player",
        on_delete=fields.CASCADE
    )
    amount = fields.BigIntField(default=0)