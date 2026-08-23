from typing import TYPE_CHECKING

from bd_models.models import Special
from django.contrib import admin

from .models import (
    AuctionBoosterRole,
    AuctionGuildConfig,
    AuctionListing,
    AuctionOffer,
    AuctionSettings,
    DirectSaleLog,
    GiveawayLog,
    HotelStock,
    ServerActivity,
    SpecialPriceModifier,
    StatBonusModifier,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(AuctionSettings)
class AuctionSettingsAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Pricing", {"fields": ["base_price", "min_price", "max_price", "excluded_rarity"]}),
        (
            "Direct sales & listings",
            {"fields": ["direct_sale_daily_limit", "max_active_listings"]},
        ),
        ("Resale shop", {"fields": ["resale_markup_percent", "max_shop_rarity"]}),
        ("Listing duration", {"fields": ["min_listing_hours", "max_listing_hours"]}),
        ("Giveaway", {"fields": ["giveaway_interval_hours", "giveaway_activity_window_hours"]}),
    ]

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return super().has_add_permission(request) and AuctionSettings.objects.first() is None

    def has_delete_permission(self, request: "HttpRequest", obj: AuctionSettings | None = None) -> bool:
        return False


@admin.register(AuctionGuildConfig)
class AuctionGuildConfigAdmin(admin.ModelAdmin):
    list_display = ("server_id", "notification_channel_id")
    search_fields = ("server_id",)


@admin.register(AuctionBoosterRole)
class AuctionBoosterRoleAdmin(admin.ModelAdmin):
    list_display = ("server_id", "role_id", "buy_discount_percent", "sell_bonus_percent")
    list_editable = ("buy_discount_percent", "sell_bonus_percent")
    list_filter = ("server_id",)
    search_fields = ("server_id", "role_id")


@admin.register(SpecialPriceModifier)
class SpecialPriceModifierAdmin(admin.ModelAdmin):
    list_display = ("special", "percent")
    list_editable = ("percent",)
    ordering = ["special__name"]

    def changelist_view(self, request: "HttpRequest", extra_context=None):
        configured_ids = set(SpecialPriceModifier.objects.values_list("special_id", flat=True))
        missing = Special.objects.exclude(id__in=configured_ids)
        SpecialPriceModifier.objects.bulk_create(
            [SpecialPriceModifier(special=special, percent=0) for special in missing]
        )
        return super().changelist_view(request, extra_context)


@admin.register(StatBonusModifier)
class StatBonusModifierAdmin(admin.ModelAdmin):
    list_display = ("value", "percent")
    list_editable = ("percent",)
    list_per_page = 100
    ordering = ["value"]

    def has_add_permission(self, request: "HttpRequest") -> bool:
        return False

    def has_delete_permission(self, request: "HttpRequest", obj: StatBonusModifier | None = None) -> bool:
        return False


@admin.register(AuctionListing)
class AuctionListingAdmin(admin.ModelAdmin):
    list_display = ("id", "seller", "server_id", "asking_price", "status", "created_at", "expires_at")
    list_filter = ("status", "server_id")
    search_fields = ("seller__discord_id",)
    autocomplete_fields = ("seller", "instance")


@admin.register(AuctionOffer)
class AuctionOfferAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "buyer", "amount", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("buyer__discord_id",)
    autocomplete_fields = ("buyer", "listing")


@admin.register(HotelStock)
class HotelStockAdmin(admin.ModelAdmin):
    list_display = ("id", "server_id", "buyout_price", "resale_price", "status", "acquired_at")
    list_filter = ("status", "server_id")
    autocomplete_fields = ("instance",)


@admin.register(DirectSaleLog)
class DirectSaleLogAdmin(admin.ModelAdmin):
    list_display = ("player", "server_id", "sale_date", "count")
    list_filter = ("server_id", "sale_date")
    search_fields = ("player__discord_id",)


@admin.register(ServerActivity)
class ServerActivityAdmin(admin.ModelAdmin):
    list_display = ("player", "server_id", "last_seen")
    list_filter = ("server_id",)
    search_fields = ("player__discord_id",)


@admin.register(GiveawayLog)
class GiveawayLogAdmin(admin.ModelAdmin):
    list_display = ("server_id", "winner", "instance", "drawn_at")
    list_filter = ("server_id",)
    search_fields = ("winner__discord_id",)
