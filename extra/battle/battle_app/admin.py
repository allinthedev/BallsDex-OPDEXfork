from typing import TYPE_CHECKING

from django.contrib import admin

from .models import BattleItem, BattleRecord, BattleSession, BattleSettings, Buff, Matchup, PlayerBattleItem

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(Buff)
class BuffAdmin(admin.ModelAdmin):
    autocomplete_fields = ("ball", "special")
    list_display = ("display", "health", "attack")
    search_fields = ("ball__country", "special__name")


@admin.register(BattleSettings)
class BattleSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            "Combat",
            {
                "fields": [
                    "attack_variance_min",
                    "attack_variance_max",
                    "crit_chance",
                    "crit_multiplier",
                    "crit_fail_multiplier",
                    "dodge_chance",
                    "heal_percent_min",
                    "heal_percent_max",
                    "heal_uses_per_battle",
                    "capacity_uses_per_battle",
                    "default_capacity_multiplier",
                    "turn_timeout_seconds",
                    "max_deck_size",
                ]
            },
        ),
        (
            "Tier-based damage scaling",
            {
                "description": (
                    "Tier = rounded rarity. A lower rarity number is a rarer/stronger card, so "
                    "\"enemy is a tier higher\" means the enemy is rarer than your attacker."
                ),
                "fields": [
                    "tier_same_multiplier",
                    "tier_enemy_1_higher_multiplier",
                    "tier_enemy_2plus_higher_multiplier",
                    "tier_enemy_1_lower_multiplier",
                    "tier_enemy_2plus_lower_multiplier",
                    "tier_enemy_2plus_lower_bonus_crit_chance",
                ],
            },
        ),
        (
            "Special card bonuses",
            {
                "description": "Flat ATK/HP bonuses for special cards in battle, matching /boss fights.",
                "fields": ["haki_special_bonus", "shiny_special_bonus", "mythical_special_bonus"],
            },
        ),
        (
            "Anti-abuse earnings",
            {
                "fields": [
                    "guaranteed_daily_wins",
                    "guaranteed_win_reward",
                    "performance_base_reward",
                    "performance_scale_min",
                    "performance_scale_max",
                    "max_rewarded_wins_per_opponent_per_day",
                ]
            },
        ),
    ]

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and BattleSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: BattleSettings | None = None) -> bool:
        return False


@admin.register(Matchup)
class MatchupAdmin(admin.ModelAdmin):
    autocomplete_fields = ("attacker", "defender")
    list_display = ("attacker", "defender", "damage_multiplier")
    search_fields = ("attacker__country", "defender__country")


@admin.register(BattleRecord)
class BattleRecordAdmin(admin.ModelAdmin):
    autocomplete_fields = ("player1", "player2", "winner")
    list_display = ("player1", "player2", "winner", "wager_amount", "winner_earnings", "turns", "created_at")
    list_filter = ("created_at",)
    search_fields = ("player1__discord_id", "player2__discord_id", "winner__discord_id")
    ordering = ["-created_at"]


@admin.register(BattleItem)
class BattleItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "effect_type", "effect_value", "enabled")
    list_editable = ("price", "enabled")
    list_filter = ("effect_type", "enabled")
    search_fields = ("name",)


@admin.register(PlayerBattleItem)
class PlayerBattleItemAdmin(admin.ModelAdmin):
    autocomplete_fields = ("player", "item")
    list_display = ("player", "item", "quantity")
    search_fields = ("player__discord_id", "item__name")


@admin.register(BattleSession)
class BattleSessionAdmin(admin.ModelAdmin):
    autocomplete_fields = ("player1", "player2")
    list_display = ("id", "channel_id", "player1", "player2", "wager_amount", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("player1__discord_id", "player2__discord_id", "channel_id")
    ordering = ["-updated_at"]
