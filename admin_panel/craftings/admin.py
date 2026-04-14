from typing import TYPE_CHECKING, Any

from django.contrib import admin
from .models import CraftingRecipe, CraftingIngredient, CraftingIngredientGroup, CraftingGroupOption
from django.utils.safestring import mark_safe

class CraftingIngredientInline(admin.TabularInline):
    model = CraftingIngredient
    extra = 1
    autocomplete_fields = ("ingredient",)
    fields = ("ingredient", "quantity") 

class CraftingGroupOptionInline(admin.TabularInline):
    model = CraftingGroupOption
    extra = 1
    autocomplete_fields = ("ball",)
    fields = ("ball",)
    
class CraftingIngredientGroupInline(admin.StackedInline):
    model = CraftingIngredientGroup
    extra = 1
    fields = ("name", "required_count")
    show_change_link = True   
    
@admin.register(CraftingRecipe)
class CraftingRecipeAdmin(admin.ModelAdmin):
    list_display = ("result",)
    inlines = [CraftingIngredientInline, CraftingIngredientGroupInline]
    search_fields = ("result__name",)
    autocomplete_fields = ("result",)  

@admin.register(CraftingIngredientGroup)
class CraftingIngredientGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "required_count", "recipe")
    inlines = [CraftingGroupOptionInline]
    search_fields = ("ball__name", "group__name") 
