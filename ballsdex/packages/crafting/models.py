from __future__ import annotations

from datetime import datetime, timedelta
from enum import IntEnum
from io import BytesIO
from typing import TYPE_CHECKING, Iterable, Tuple, Type

import discord
from discord.utils import format_dt
from tortoise import exceptions, fields, models, signals, timezone, validators
from tortoise.contrib.postgres.indexes import PostgreSQLIndex
from tortoise.expressions import Q

from ballsdex.core.image_generator.image_gen import draw_card
from ballsdex.settings import settings

if TYPE_CHECKING:
    from tortoise.backends.base.client import BaseDBAsyncClient


class CraftingRecipe(models.Model):
    id = fields.IntField(pk=True)
    result = fields.ForeignKeyField("models.Ball", related_name="crafted_by")

    class Meta:
        table = "craftingrecipe"

    def __str__(self) -> str:
        return str(self.pk)

class CraftingIngredient(models.Model):
    id = fields.IntField(pk=True)
    recipe = fields.ForeignKeyField("models.CraftingRecipe", related_name="ingredients")
    ingredient = fields.ForeignKeyField("models.Ball", null=True, related_name="+")  
    quantity = fields.IntField(default=1)

    class Meta:
        table = "craftingingredient"
        unique_together = ("recipe", "ingredient")  
        
    def __str__(self) -> str:
        return str(self.pk)
        
class CraftingIngredientGroup(models.Model):
    id = fields.IntField(pk=True)
    recipe = fields.ForeignKeyField("models.CraftingRecipe", related_name="ingredient_groups")
    name = fields.CharField(max_length=100)  # e.g., "European Countries"
    required_count = fields.IntField(default=1)  # How many from this group needed

    class Meta:
        table = "craftingingredientgroup"

    def __str__(self) -> str:
        return f"{self.name} (choose {self.required_count})"

class CraftingGroupOption(models.Model):
    id = fields.IntField(pk=True)
    group = fields.ForeignKeyField("models.CraftingIngredientGroup", related_name="options")
    ball = fields.ForeignKeyField("models.Ball", related_name="group_memberships")

    class Meta:
        table = "craftinggroupoption"
        unique_together = ("group", "ball")

    def __str__(self) -> str:
        return f"{self.ball} in {self.group.name}" if hasattr(self, 'ball') and hasattr(self, 'group') else str(self.pk)
