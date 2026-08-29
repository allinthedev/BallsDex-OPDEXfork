from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import F, Q


class AugmentSettings(models.Model):
    # Rarity-based portion of the cost. Independent of the card's current stats.
    rarity_cost_min = models.PositiveIntegerField(
        default=2500, help_text="Base augment cost in berries for the rarest cards (rarity value of 1)."
    )
    rarity_cost_max = models.PositiveIntegerField(
        default=50,
        help_text="Base augment cost in berries for common cards, once rarity_cost_floor_at is reached.",
    )
    rarity_cost_floor_at = models.FloatField(
        default=230.0,
        help_text="Rarity value at which the base cost bottoms out at rarity_cost_max. "
        "Cost decreases linearly between rarity 1 and this value.",
    )

    # How much a single attempt moves each stat, win or lose.
    min_roll = models.PositiveIntegerField(
        default=1, help_text="Minimum stat change (percentage points) applied to each stat, win or lose."
    )
    max_roll = models.PositiveIntegerField(
        default=5, help_text="Maximum stat change (percentage points) applied to each stat, win or lose."
    )

    # Cumulative stat cap (attack_bonus + health_bonus) beyond which a card is treated as fully
    # maxed out for cost/success purposes, even if stats could theoretically climb higher still.
    # Default of 30 means a +14%/+18% card (cumulative 32) already sits at the worst-case tier.
    high_stat_threshold = models.FloatField(
        default=30.0,
        help_text="Cumulative attack_bonus + health_bonus (%) at which a card is considered maxed out.",
    )

    # Success rate scaling based on how close to maxed out (see high_stat_threshold) a card is.
    min_success_rate = models.FloatField(
        default=10.0, help_text="Success rate (%) applied when a card's stats are already maxed out."
    )
    max_success_rate = models.FloatField(
        default=100.0, help_text="Success rate (%) applied when a card's stats are at their worst."
    )

    # Cost scaling based on how close to maxed out (see high_stat_threshold) a card is.
    min_cost_multiplier = models.FloatField(
        default=0.5, help_text="Cost multiplier applied when a card's stats are at their worst."
    )
    max_cost_multiplier = models.FloatField(
        default=4.0,
        help_text="Cost multiplier applied when a card's stats are already maxed out. "
        "Combined with rarity_cost_min, this sets the absolute maximum augment cost "
        "(e.g. 2500 * 4.0 = 10 000 berries for a maxed-out rarity-1 card).",
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
        db_table = "augmentsettings"
        constraints = [
            models.CheckConstraint(condition=Q(min_roll__lte=F("max_roll")), name="augmentsettings_roll_min_lte_max"),
            models.CheckConstraint(
                condition=Q(min_success_rate__gte=0) & Q(max_success_rate__lte=100),
                name="augmentsettings_success_rate_bounds",
            ),
            models.CheckConstraint(
                condition=Q(min_success_rate__lte=F("max_success_rate")),
                name="augmentsettings_success_rate_min_lte_max",
            ),
            models.CheckConstraint(
                condition=Q(rarity_cost_floor_at__gt=1), name="augmentsettings_rarity_cost_floor_gt_1"
            ),
            models.CheckConstraint(
                condition=Q(high_stat_threshold__gt=0), name="augmentsettings_high_stat_threshold_gt_0"
            ),
        ]

    def __str__(self) -> str:
        return "Augment Settings"
