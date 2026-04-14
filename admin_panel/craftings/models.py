from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable, cast

from django.contrib import admin
from django.core.cache import cache
from django.db import models
from django.utils.safestring import SafeText, mark_safe
from django.utils.timezone import now
from bd_models.models import Ball, Player 
from ballsdex.settings import settings 

class CraftingRecipe(models.Model):
    result = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="crafted_by") 
    
    class Meta:
        managed = True
        db_table = "craftingrecipe"

    def __str__(self):
        if self.result:
            return f"{self.result} Recipe"
        return "Unnamed Crafting Recipe"


class CraftingIngredient(models.Model):
    recipe = models.ForeignKey("CraftingRecipe", on_delete=models.CASCADE, related_name="ingredients")
    ingredient = models.ForeignKey(Ball, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        managed = True
        db_table = "craftingingredient" 
        unique_together = ("recipe", "ingredient") 
        
    def __str__(self):
        if self.recipe:
            return f"{self.recipe} Recipe"
        return "Unnamed Crafting Recipe"

class CraftingIngredientGroup(models.Model):
    recipe = models.ForeignKey("CraftingRecipe", on_delete=models.CASCADE, related_name="ingredient_groups")
    name = models.CharField(max_length=100)
    required_count = models.PositiveIntegerField(default=1)

    class Meta:
        managed=True
        db_table="craftingingredientgroup"

    def __str__(self):
        return f"{self.name} (need {self.required_count})"


class CraftingGroupOption(models.Model):
    group = models.ForeignKey("CraftingIngredientGroup", on_delete=models.CASCADE, related_name="options")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="group_memberships")

    class Meta:
        managed=True
        db_table= "craftinggroupoption"
        unique_together = ("group", "ball")

    def __str__(self):
        return f"{self.ball} in {self.group.name}"
