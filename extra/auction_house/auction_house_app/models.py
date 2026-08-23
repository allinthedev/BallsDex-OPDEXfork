from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import F, Q

from bd_models.models import BallInstance, Player, Special

HOTEL_PLAYER_DISCORD_ID = 0


class AuctionSettings(models.Model):
    """
    Bot-wide tuning for the Hotel de Vente. Role IDs live on AuctionGuildConfig instead,
    since a Discord role only means something inside one specific server.
    """

    base_price = models.PositiveBigIntegerField(
        default=70000,
        help_text="Reference price used by the pricing formula. Kept for parity with the original "
        "pricing tool this formula was ported from.",
    )
    min_price = models.PositiveBigIntegerField(
        default=200, help_text="Floor applied to the computed price of any card (the most common cards)."
    )
    max_price = models.PositiveBigIntegerField(
        default=300000, help_text="Cap applied to the computed price of any card (the rarest cards, T1)."
    )
    excluded_rarity = models.FloatField(
        default=0.0,
        help_text="Cards with this exact rarity value can never be sold to the Hotel or listed for auction.",
    )
    max_shop_rarity = models.FloatField(
        null=True,
        blank=True,
        help_text="If set, only cards with a rarity between excluded_rarity and this value show up in Buggy's "
        "resale shop (e.g. setting 50 means the shop only lists cards with rarity between 0 and 50). Buggy still "
        "buys every non-special card directly regardless of this setting — this only limits what he resells. "
        "Leave blank for no limit.",
    )

    direct_sale_daily_limit = models.PositiveIntegerField(
        default=10, help_text="Maximum number of cards a player can sell directly to the Hotel per day."
    )
    max_active_listings = models.PositiveIntegerField(
        default=5, help_text="Maximum number of cards a player can have listed for auction at once."
    )
    resale_markup_percent = models.PositiveIntegerField(
        default=10, help_text="Markup applied when the Hotel relists a card it bought directly from a player."
    )

    min_listing_hours = models.PositiveIntegerField(
        default=1, help_text="Minimum duration a player can choose when listing a card for auction."
    )
    max_listing_hours = models.PositiveIntegerField(
        default=72, help_text="Maximum duration a player can choose when listing a card for auction."
    )

    giveaway_interval_hours = models.PositiveIntegerField(
        default=12, help_text="How often the Hotel raffles off one of its unsold cards, per server."
    )
    giveaway_activity_window_hours = models.PositiveIntegerField(
        default=24, help_text="A player must have used a bot command within this window to be eligible to win."
    )

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    async def aload(cls):
        return await sync_to_async(cls.load)()

    class Meta:
        managed = True
        db_table = "auctionsettings"
        constraints = [
            models.CheckConstraint(condition=Q(min_price__lte=F("max_price")), name="auctionsettings_price_min_lte_max"),
            models.CheckConstraint(
                condition=Q(min_listing_hours__lte=F("max_listing_hours")),
                name="auctionsettings_listing_hours_min_lte_max",
            ),
        ]

    def __str__(self) -> str:
        return "Auction House Settings"


class AuctionGuildConfig(models.Model):
    """Per-server configuration, since role IDs and the Hotel's stock are server-scoped."""

    server_id = models.BigIntegerField(unique=True, help_text="Discord server ID this configuration applies to.")
    notification_channel_id = models.BigIntegerField(
        null=True, blank=True, help_text="Channel where sale notifications (accepted offers) are posted."
    )

    class Meta:
        managed = True
        db_table = "auctionguildconfig"

    def __str__(self) -> str:
        return f"Guild config for {self.server_id}"


class AuctionBoosterRole(models.Model):
    """
    A role that grants a booster discount/bonus on Hotel transactions. Multiple roles can be
    configured per server, each with its own percentages (e.g. tiered supporter roles).
    """

    server_id = models.BigIntegerField(help_text="Discord server ID this role applies to.")
    role_id = models.BigIntegerField(help_text="Role ID granting this booster tier.")
    buy_discount_percent = models.PositiveIntegerField(
        default=5, help_text="Discount this role gets when buying from the Hotel's resale shop."
    )
    sell_bonus_percent = models.PositiveIntegerField(
        default=5, help_text="Bonus this role gets when selling directly to the Hotel."
    )

    class Meta:
        managed = True
        db_table = "auctionboosterrole"
        unique_together = (("server_id", "role_id"),)
        indexes = (models.Index(fields=("server_id",)),)

    def __str__(self) -> str:
        return f"Booster role {self.role_id} in {self.server_id} (+{self.sell_bonus_percent}%/-{self.buy_discount_percent}%)"


class SpecialPriceModifier(models.Model):
    special = models.OneToOneField(Special, on_delete=models.CASCADE, related_name="auction_price_modifier")
    special_id: int
    percent = models.IntegerField(default=0, help_text="Price bonus/malus for this special, in percent.")

    class Meta:
        managed = True
        db_table = "auctionspecialpricemodifier"

    def __str__(self) -> str:
        return f"{self.special} ({self.percent:+d}%)"


class StatBonusModifier(models.Model):
    value = models.IntegerField(unique=True, help_text="Average of a card's attack and health bonus.")
    percent = models.IntegerField(default=0, help_text="Price bonus/malus applied for this stat average, in percent.")

    class Meta:
        managed = True
        db_table = "auctionstatbonusmodifier"
        ordering = ["value"]
        constraints = [
            models.CheckConstraint(condition=Q(value__gte=-40) & Q(value__lte=40), name="auctionstatbonusmodifier_range")
        ]

    def __str__(self) -> str:
        return f"{self.value:+d} ({self.percent:+d}%)"


class AuctionListing(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SOLD = "sold", "Sold"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    instance = models.OneToOneField(BallInstance, on_delete=models.CASCADE, related_name="auction_listing")
    seller = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_listings")
    server_id = models.BigIntegerField()
    asking_price = models.PositiveBigIntegerField()
    duration_hours = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    offers: models.QuerySet["AuctionOffer"]

    class Meta:
        managed = True
        db_table = "auctionlisting"
        indexes = (
            models.Index(fields=("server_id", "status")),
            models.Index(fields=("seller", "status")),
            models.Index(fields=("status", "expires_at")),
        )

    def __str__(self) -> str:
        return f"Listing #{self.pk} ({self.status})"


class AuctionOffer(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"
        REFUNDED = "refunded", "Refunded"

    listing = models.ForeignKey(AuctionListing, on_delete=models.CASCADE, related_name="offers")
    buyer = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_offers")
    amount = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctionoffer"
        indexes = (
            models.Index(fields=("listing", "status")),
            models.Index(fields=("buyer", "status")),
        )

    def __str__(self) -> str:
        return f"Offer #{self.pk} on listing #{self.listing_id} ({self.status})"


class HotelStock(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        SOLD = "sold", "Sold"
        GIVEN_AWAY = "given_away", "Given away"

    instance = models.OneToOneField(BallInstance, on_delete=models.CASCADE, related_name="hotel_stock")
    server_id = models.BigIntegerField()
    buyout_price = models.PositiveBigIntegerField(help_text="What the Hotel paid the original seller.")
    resale_price = models.PositiveBigIntegerField(help_text="Price the Hotel resells this card for.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    acquired_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctionhotelstock"
        indexes = (models.Index(fields=("server_id", "status")),)

    def __str__(self) -> str:
        return f"Hotel stock #{self.pk} ({self.status})"


class DirectSaleLog(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_direct_sales")
    server_id = models.BigIntegerField()
    sale_date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        managed = True
        db_table = "auctiondirectsalelog"
        unique_together = (("player", "server_id", "sale_date"),)

    def __str__(self) -> str:
        return f"{self.player} sold {self.count} on {self.sale_date} ({self.server_id})"


class ServerActivity(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_activity")
    server_id = models.BigIntegerField()
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "auctionserveractivity"
        unique_together = (("player", "server_id"),)
        indexes = (models.Index(fields=("server_id", "last_seen")),)

    def __str__(self) -> str:
        return f"{self.player} last seen {self.last_seen} in {self.server_id}"


class GiveawayLog(models.Model):
    server_id = models.BigIntegerField()
    winner = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="auction_giveaway_wins")
    instance = models.ForeignKey(
        BallInstance, on_delete=models.SET_NULL, null=True, blank=True, related_name="auction_giveaway_logs"
    )
    drawn_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "auctiongiveawaylog"
        indexes = (models.Index(fields=("server_id", "drawn_at")),)

    def __str__(self) -> str:
        return f"Giveaway in {self.server_id} won by {self.winner} at {self.drawn_at}"


def get_hotel_player_sync() -> Player:
    obj, _ = Player.objects.get_or_create(discord_id=HOTEL_PLAYER_DISCORD_ID)
    return obj


async def get_hotel_player() -> Player:
    return await sync_to_async(get_hotel_player_sync)()
