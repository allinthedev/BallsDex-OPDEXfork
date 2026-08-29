from typing import Iterable

from asgiref.sync import sync_to_async
from django.db import models
from django.db.models import F, Q
from django.forms import ValidationError

from bd_models.models import Ball, BallInstance, Player, Special, balls, specials


class Buff(models.Model):
    ball = models.OneToOneField(
        Ball, on_delete=models.CASCADE, null=True, blank=True, help_text="Ball that will receive an increase"
    )
    ball_id: int | None
    special = models.OneToOneField(
        Special, on_delete=models.CASCADE, null=True, blank=True, help_text="Specials that will receive an increase"
    )
    special_id: int | None
    health = models.IntegerField(default=0, help_text="Amount of health to add")
    attack = models.IntegerField(default=0, help_text="Amount of attack to add")

    @classmethod
    def get_buff(cls, instance: "BallInstance"):
        buff = cls.objects.filter(ball=instance.countryball).first()
        if not buff:
            special = instance.specialcard
            if special:
                buff = cls.objects.filter(special=special).first()
        return buff

    @classmethod
    async def aget_buff(cls, instance: "BallInstance"):
        return await sync_to_async(cls.get_buff)(instance)

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_ball = self.ball is not None
        has_special = self.special is not None
        if not has_ball and not has_special:
            raise ValidationError("You must provide either a ball or a special.")

        if has_ball and has_special:
            raise ValidationError("You cannot set both a ball and a special.")

        return super().save(force_insert, force_update, using, update_fields)

    @property
    def cached_ball(self):
        return balls.get(self.ball_id) or self.ball if self.ball_id else None

    @property
    def cached_special(self):
        return specials.get(self.special_id) or self.special if self.special_id else None

    class Meta:
        managed = True
        db_table = "buff"

    def display(self):
        if self.cached_ball:
            text = f"{self.cached_ball.country} "
        elif self.cached_special:
            text = f"{self.cached_special.name} "
        else:
            text = ""
        return f"{text} buff"

    def __str__(self):
        return self.display()


class BattleSettings(models.Model):
    # Combat
    attack_variance_min = models.FloatField(default=0.6, help_text="Lowest multiplier applied to a hit's base damage.")
    attack_variance_max = models.FloatField(
        default=1.0, help_text="Highest multiplier applied to a hit's base damage."
    )
    crit_chance = models.FloatField(default=0.5, help_text="Chance (0-1) that a Crit Gamble action lands.")
    crit_multiplier = models.FloatField(default=2.0, help_text="Damage multiplier on a successful Crit Gamble.")
    crit_fail_multiplier = models.FloatField(default=0.5, help_text="Damage multiplier on a missed Crit Gamble.")
    dodge_chance = models.FloatField(default=0.15, help_text="Chance (0-1) that any damaging action is dodged.")
    heal_percent_min = models.FloatField(default=25.0, help_text="Minimum %% of max health restored by Heal.")
    heal_percent_max = models.FloatField(default=45.0, help_text="Maximum %% of max health restored by Heal.")
    heal_uses_per_battle = models.PositiveIntegerField(
        default=2, help_text="How many times a single card can use Heal in one battle."
    )
    capacity_uses_per_battle = models.PositiveIntegerField(
        default=1, help_text="How many times a single card can use its Capacity ability in one battle."
    )
    default_capacity_multiplier = models.FloatField(
        default=1.5,
        help_text="Damage multiplier used by the Capacity action when a card's capacity_logic is empty.",
    )
    turn_timeout_seconds = models.PositiveIntegerField(
        default=60, help_text="If the active player doesn't act in time, the turn auto-resolves as an Attack."
    )
    max_deck_size = models.PositiveIntegerField(default=4, help_text="Default deck size for /battle start.")

    # Tier-based damage scaling. "Tier" = round(Ball.rarity); since a LOWER rarity number means a
    # RARER/stronger card in this game, "enemy is a tier higher" means the enemy is rarer (harder
    # matchup, less damage dealt) and "enemy is a tier lower" means the enemy is more common
    # (easier matchup, more damage dealt). Applies to every damaging action (Attack, Crit Gamble,
    # Capacity), stacking multiplicatively with the lore Matchup multiplier.
    tier_same_multiplier = models.FloatField(default=0.7, help_text="Damage multiplier vs. an equal-tier enemy.")
    tier_enemy_1_higher_multiplier = models.FloatField(
        default=0.5, help_text="Damage multiplier vs. an enemy 1 tier higher (rarer)."
    )
    tier_enemy_2plus_higher_multiplier = models.FloatField(
        default=0.3, help_text="Damage multiplier vs. an enemy 2+ tiers higher (rarer)."
    )
    tier_enemy_1_lower_multiplier = models.FloatField(
        default=0.9, help_text="Damage multiplier vs. an enemy 1 tier lower (more common)."
    )
    tier_enemy_2plus_lower_multiplier = models.FloatField(
        default=1.0, help_text="Damage multiplier vs. an enemy 2+ tiers lower (more common)."
    )
    tier_enemy_2plus_lower_bonus_crit_chance = models.FloatField(
        default=0.10,
        help_text="Extra critical-strike chance (0-1) added to ANY damaging action vs. an enemy 2+ tiers lower.",
    )

    # Special-card flat stat bonuses in battle, matching the existing /boss fight boosts exactly.
    haki_special_bonus = models.PositiveIntegerField(
        default=500, help_text="Flat ATK and HP bonus for Haki Infused (⚡) special cards, same as /boss."
    )
    shiny_special_bonus = models.PositiveIntegerField(
        default=1000, help_text="Flat ATK and HP bonus for Shiny (✨) special cards, same as /boss."
    )
    mythical_special_bonus = models.PositiveIntegerField(
        default=1500, help_text="Flat ATK and HP bonus for Mythical (🔮) special cards, same as /boss."
    )

    # Anti-abuse earnings
    guaranteed_daily_wins = models.PositiveIntegerField(
        default=3, help_text="How many wins per rolling 24h pay the flat guaranteed_win_reward."
    )
    guaranteed_win_reward = models.PositiveIntegerField(
        default=50, help_text="Flat berries paid for each of the first guaranteed_daily_wins wins per day."
    )
    performance_base_reward = models.PositiveIntegerField(
        default=30, help_text="Base berries for wins past the guaranteed daily count, before scaling."
    )
    performance_scale_min = models.FloatField(
        default=0.5, help_text="Minimum scale applied to performance_base_reward (beating a much weaker opponent)."
    )
    performance_scale_max = models.FloatField(
        default=2.0, help_text="Maximum scale applied to performance_base_reward (beating a much stronger opponent)."
    )
    max_rewarded_wins_per_opponent_per_day = models.PositiveIntegerField(
        default=1,
        help_text="Wins past this many against the SAME opponent in a day are still recorded but pay 0 berries "
        "(blunts the simplest two-account farming loop).",
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
        db_table = "battlesettings"
        constraints = [
            models.CheckConstraint(
                condition=Q(attack_variance_min__lte=F("attack_variance_max")),
                name="battlesettings_variance_min_lte_max",
            ),
            models.CheckConstraint(
                condition=Q(heal_percent_min__lte=F("heal_percent_max")), name="battlesettings_heal_min_lte_max"
            ),
            models.CheckConstraint(
                condition=Q(performance_scale_min__lte=F("performance_scale_max")),
                name="battlesettings_perf_scale_min_lte_max",
            ),
            models.CheckConstraint(
                condition=Q(crit_chance__gte=0) & Q(crit_chance__lte=1), name="battlesettings_crit_chance_bounds"
            ),
            models.CheckConstraint(
                condition=Q(dodge_chance__gte=0) & Q(dodge_chance__lte=1), name="battlesettings_dodge_chance_bounds"
            ),
            models.CheckConstraint(
                condition=Q(tier_enemy_2plus_lower_bonus_crit_chance__gte=0)
                & Q(tier_enemy_2plus_lower_bonus_crit_chance__lte=1),
                name="battlesettings_tier_bonus_crit_bounds",
            ),
        ]

    def __str__(self) -> str:
        return "Battle Settings"


class Matchup(models.Model):
    """
    A lore-based rivalry: when `attacker` fights `defender`, damage dealt is scaled by
    `damage_multiplier` (e.g. Akainu vs Ace = 1.3 for a 30%% edge). Neutral (no row) means ×1.0.
    Not symmetric — add the reverse row too if the rivalry should cut both ways.
    """

    attacker = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="matchups_as_attacker")
    attacker_id: int
    defender = models.ForeignKey(Ball, on_delete=models.CASCADE, related_name="matchups_as_defender")
    defender_id: int
    damage_multiplier = models.FloatField(
        default=1.25, help_text="Damage multiplier applied when attacker hits defender. 1.0 = no effect."
    )

    class Meta:
        managed = True
        db_table = "battlematchup"
        unique_together = (("attacker", "defender"),)
        constraints = [
            models.CheckConstraint(condition=~Q(attacker=F("defender")), name="battlematchup_attacker_neq_defender"),
        ]

    def __str__(self) -> str:
        return f"{self.attacker.country} > {self.defender.country} (x{self.damage_multiplier})"


class BattleRecord(models.Model):
    """
    One row per finished battle. Used as the source of truth for the 1v1 leaderboard and for the
    anti-abuse earnings cap (queried by rolling 24h window) instead of a resettable aggregate
    counter, so admins can see exactly who fought who, for how much, and why a payout was capped.
    """

    player1 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="battles_as_player1")
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="battles_as_player2")
    winner = models.ForeignKey(
        Player, on_delete=models.SET_NULL, null=True, blank=True, related_name="battles_won"
    )
    wager_amount = models.PositiveBigIntegerField(default=0, help_text="Berries each side staked, if any.")
    winner_earnings = models.PositiveBigIntegerField(
        default=0, help_text="Anti-abuse win reward actually paid out (0 if capped that day)."
    )
    turns = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        managed = True
        db_table = "battlerecord"
        indexes = [
            models.Index(fields=["player1"]),
            models.Index(fields=["player2"]),
            models.Index(fields=["winner"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"Battle #{self.pk}: {self.player1_id} vs {self.player2_id}"


class BattleItemEffect(models.TextChoices):
    EXTRA_HEAL = "extra_heal", "Bonus %% healed on this turn's Heal action"
    ATTACK_BOOST = "attack_boost", "Damage multiplier on this turn's Attack/Crit Gamble"
    GUARANTEED_CRIT = "guaranteed_crit", "This turn's Crit Gamble always lands"


class BattleItem(models.Model):
    name = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=256, blank=True, null=True)
    price = models.PositiveIntegerField(help_text="Cost in berries.")
    effect_type = models.CharField(max_length=32, choices=BattleItemEffect.choices)
    effect_value = models.FloatField(help_text="Meaning depends on effect_type (a multiplier, a %%, ...).")
    emoji_id = models.BigIntegerField(null=True, blank=True, help_text="Optional custom emoji ID for this item.")
    enabled = models.BooleanField(default=True)

    class Meta:
        managed = True
        db_table = "battleitem"

    def __str__(self) -> str:
        return self.name


class PlayerBattleItem(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="battle_items")
    item = models.ForeignKey(BattleItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=0)

    class Meta:
        managed = True
        db_table = "playerbattleitem"
        unique_together = (("player", "item"),)

    def __str__(self) -> str:
        return f"{self.player_id} x{self.quantity} {self.item_id}"


class BattleSessionStatus(models.TextChoices):
    PROPOSED = "proposed", "Proposed"
    ACTIVE = "active", "Active"
    FINISHED = "finished", "Finished"
    CANCELLED = "cancelled", "Cancelled"


class BattleSession(models.Model):
    """
    Persisted battle state. Battles used to live purely in-memory, which was fine when nothing
    was at stake — now that a battle can escrow a berry wager, a bot restart mid-battle must be
    able to find and refund it instead of silently losing track of the money.
    """

    channel_id = models.BigIntegerField()
    player1 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="battle_sessions_as_player1")
    player2 = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="battle_sessions_as_player2")
    wager_amount = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=BattleSessionStatus.choices, default=BattleSessionStatus.PROPOSED)
    state = models.JSONField(default=dict, blank=True, help_text="Decks, HP, whose turn, use counters.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "battlesession"
        indexes = [models.Index(fields=["channel_id"]), models.Index(fields=["status"])]

    def __str__(self) -> str:
        return f"BattleSession #{self.pk} ({self.status})"
