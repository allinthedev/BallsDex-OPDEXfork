from tortoise import models, fields
from tortoise.contrib.postgres.indexes import PostgreSQLIndex
from .models import Ball, Player, Special, balls, specials

class Collectible(models.Model):
    name = fields.CharField(max_length=64, unique=True)
    description = fields.TextField(
        null=True, default=None, description="An optional descripcion for this collectible"
    )
    emoji_id = fields.BigIntField(description="Emoji ID of this collectible")
    price = fields.BigIntField(
        null=True,
        default=None,
        description="The price of this collectible. If blanks, it will free."
    )
    created_at = fields.DatetimeField(auto_now_add=True)

    # Requirement Values
    ball: fields.ForeignKeyNullableRelation[Ball] = fields.ForeignKeyField(
        "models.Ball",
        on_delete=fields.SET_NULL,
        null=True,
        default=None,
        description="An optional requirement that specifies a required ball."
    )
    ball_id: int | None
    special: fields.ForeignKeyNullableRelation[Special] = fields.ForeignKeyField(
        "models.Special",
        on_delete=fields.SET_NULL,
        null=True,
        default=None,
        description="An optional requirement that specifies a required special."
    )
    special_id: int | None
    amount = fields.IntField(null=True, default=None)

    @property
    def is_not_requirements(self) -> bool:
        return self.amount is None and self.ball_id is None and self.special_id is None

    @property
    def cached_ball(self) -> Ball | None:
        return balls.get(self.ball_id) or self.ball if self.ball_id else None
    
    @property
    def cached_special(self) -> Special | None:
        return specials.get(self.special_id) or self.special if self.special_id else None

    class Meta:
        indexes = [
            PostgreSQLIndex(fields=["name"]),
            PostgreSQLIndex(fields=["ball_id"]),
            PostgreSQLIndex(fields=["special_id"])
        ]

class CollectibleInstance(models.Model):
    player: fields.ForeignKeyRelation[Player] = fields.ForeignKeyField(
        "models.Player",
        on_delete=fields.CASCADE,
        related_name="collectibles"
    )
    collectible: fields.ForeignKeyRelation[Collectible] = fields.ForeignKeyField(
        "models.Collectible",
        on_delete=fields.CASCADE
    )
    obtained_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            PostgreSQLIndex(fields=["player_id"]),
            PostgreSQLIndex(fields=["collectible_id"])
        ]
