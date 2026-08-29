"""
Pure calculation helpers for the Augment feature.

Kept separate from models.py and the cog so the cost/success-rate math can be read
(and adjusted) in one place, independently of Discord or Django plumbing.
"""

from typing import TYPE_CHECKING

from settings.models import settings as bot_settings

if TYPE_CHECKING:
    from bd_models.models import BallInstance

    from .models import AugmentSettings


def stat_position(settings: "AugmentSettings", instance: "BallInstance") -> float:
    """
    How close to "maxed out" a card's stats currently are, from 0 (worst possible cumulative
    stats) to 1 (cumulative attack_bonus + health_bonus has reached high_stat_threshold).

    Cards past the threshold are all treated as equally maxed out for cost/success purposes,
    even though their stats could theoretically climb higher still.
    """
    cumulative = instance.attack_bonus + instance.health_bonus
    floor = -(bot_settings.max_attack_bonus + bot_settings.max_health_bonus)
    ceiling = settings.high_stat_threshold
    if ceiling <= floor:
        return 1.0
    return min(1.0, max(0.0, (cumulative - floor) / (ceiling - floor)))


def base_cost(settings: "AugmentSettings", rarity: float) -> int:
    """Base berry cost derived only from the card's rarity, independent of its current stats."""
    if rarity <= 1:
        return settings.rarity_cost_min
    if rarity >= settings.rarity_cost_floor_at:
        return settings.rarity_cost_max
    ratio = (rarity - 1) / (settings.rarity_cost_floor_at - 1)
    span = settings.rarity_cost_min - settings.rarity_cost_max
    return round(settings.rarity_cost_min - span * ratio)


def cost(settings: "AugmentSettings", instance: "BallInstance") -> int:
    """Full berry cost to attempt an augment on this card."""
    position = stat_position(settings, instance)
    multiplier = settings.min_cost_multiplier + (settings.max_cost_multiplier - settings.min_cost_multiplier) * position
    return max(1, round(base_cost(settings, instance.countryball.rarity) * multiplier))


def success_rate(settings: "AugmentSettings", instance: "BallInstance") -> float:
    """Chance (0-100) that an augment attempt on this card succeeds."""
    position = stat_position(settings, instance)
    rate = settings.max_success_rate - (settings.max_success_rate - settings.min_success_rate) * position
    return min(100.0, max(0.0, rate))
