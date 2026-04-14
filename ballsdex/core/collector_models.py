from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import models, fields
from tortoise.contrib.postgres.indexes import PostgreSQLIndex

from ballsdex.core.models import balls, specials

if TYPE_CHECKING:
    from ballsdex.core.models import Ball, Player, Special

class Collector(models.Model):
    name = fields.CharField(max_length=64)
    ball: fields.ForeignKeyNullableRelation["Ball"] = fields.ForeignKeyField(
        "models.Ball",
        on_delete=fields.CASCADE,
        null=True,
        default=None,
    )
    ball_id: int
    special: fields.ForeignKeyNullableRelation["Special"] = fields.ForeignKeyField(
        "models.Special",
        on_delete=fields.SET_NULL,
        null=True,
        default=None
    )
    special_id: int | None
    start_date = fields.DatetimeField(null=True, default=None)
    end_date = fields.DatetimeField(null=True, default=None)
    tradeable = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    requirements: fields.BackwardFKRelation[CollectorRequirement]

    @property
    def cached_ball(self) -> "Ball | None":
        return balls.get(self.ball_id, self.ball) if self.ball_id else None
    
    @property
    def cached_special(self) -> "Special | None":
        return specials.get(self.special_id, self.special) if self.special_id else None

    def __str__(self):
        return self.name
    
    class Meta:
        indexes = [
            PostgreSQLIndex(fields=("ball_id",)),
            PostgreSQLIndex(fields=("special_id",)),
            PostgreSQLIndex(fields=("amount",)),
        ]

class CollectorRequirement(models.Model):
    collector: fields.ForeignKeyRelation[Collector] = fields.ForeignKeyField(
        "models.Collector",
        on_delete=fields.CASCADE,
        related_name="requirements"
    )
    ball: fields.ForeignKeyNullableRelation["Ball"] = fields.ForeignKeyField(
        "models.Ball",
        on_delete=fields.SET_NULL,
        null=True,
        default=None
    )
    ball_id: int
    special: fields.ForeignKeyNullableRelation["Special"] = fields.ForeignKeyField(
        "models.Special",
        on_delete=fields.SET_NULL,
        null=True,
        default=None
    )
    special_id: int | None
    amount = fields.IntField(default=1)
    delete_balls = fields.BooleanField(
        default=False, 
        description="If a user meets all requirements, will the required balls be removed? "
    )

    @property
    def cached_ball(self):
        return balls.get(self.ball_id, self.ball)
    
    @property
    def cached_special(self) -> "Special | None":
        return specials.get(self.special_id, self.special) if self.special_id else None
    
    class Meta:
        indexes = [
            PostgreSQLIndex(fields=("collector_id",)),
            PostgreSQLIndex(fields=("ball_id",)),
            PostgreSQLIndex(fields=("special_id",)),
            PostgreSQLIndex(fields=("amount",)),
        ]

class CollectorInstance(models.Model):
    player: fields.ForeignKeyRelation["Player"] = fields.ForeignKeyField(
        "models.Player",
        on_delete=fields.CASCADE
    )
    collector: fields.ForeignKeyRelation[Collector] = fields.ForeignKeyField(
        "models.Collector",
        on_delete=fields.CASCADE
    )

    class Meta:
        unique_together = ("player", "collector")
        indexes = [
            PostgreSQLIndex(fields=("collector_id",)),
            PostgreSQLIndex(fields=("player_id",)),
        ]
