from tortoise import models, fields
from .models import Player, Special

class Item(models.Model):
    name = fields.CharField(max_length=64)
    description = fields.TextField(null=True, description="An optional description for the item")
    prize = fields.BigIntField(null=True, description="The prize of the item. If blanks, it will free")
    emoji_id = fields.BigIntField(null=True, default=None)
    minimum_rarity = fields.FloatField(description="Minimum rarity range.")
    maximum_rarity = fields.FloatField(description="Maximum rarity range.")
    created_at = fields.DatetimeField(auto_now_add=True)
    special: fields.ForeignKeyNullableRelation[Special] = fields.ForeignKeyField(
        "models.Special",
        on_delete=fields.SET_NULL,
        null=True,
        default=None,
        description="The special of the item (optional)"
    )

    def __str__(self) -> str:
        return self.name

class CurrencySettings(models.Model):
    name = fields.CharField(max_length=64)
    plural_name = fields.CharField(max_length=64)
    emoji_id = fields.BigIntField(description="Emoji id of the currency", null=True)

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