from typing import TYPE_CHECKING

from django.contrib import admin

from .models import AugmentSettings

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(AugmentSettings)
class AugmentSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Rarity cost", {"fields": ["rarity_cost_min", "rarity_cost_max", "rarity_cost_floor_at"]}),
        ("Stat roll", {"fields": ["min_roll", "max_roll"]}),
        ("Maxed-out threshold", {"fields": ["high_stat_threshold"]}),
        ("Success rate", {"fields": ["min_success_rate", "max_success_rate"]}),
        ("Cost multiplier", {"fields": ["min_cost_multiplier", "max_cost_multiplier"]}),
    ]

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and AugmentSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: AugmentSettings | None = None) -> bool:
        return False
