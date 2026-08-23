"""
Pure calculation helpers for the Hotel de Vente pricing formula.

Ported from the DexValueCalc tool the server owner uses. Kept as-is on purpose,
quirks included: `base_price` cancels out of the rarity formula algebraically, and
the curve is nearly flat because of the tiny exponent. `min_price`/`max_price` are
what actually separate rare cards from common ones in practice.

Unlike the original tool, there is no "overall 1-25" bucket bonus here: OPDex's data
model has no equivalent field, so only the rarity base, stats bonus and special bonus
are implemented.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bd_models.models import BallInstance

    from .models import AuctionSettings

# Formula constants ported from the original pricing tool.
_A = 159528107.1046
_B = -0.9627
_C = 0.0001
_D = -159457804.3152


def base_value(rarity: float, settings: "AuctionSettings") -> int:
    """
    Base card value derived from rarity only, clamped to [min_price, max_price].

    `settings.base_price` is intentionally unused here: in the original formula it's both
    divided and multiplied back in, cancelling out algebraically. That division-then-
    multiplication is dropped rather than reproduced, since it's a no-op for any nonzero
    base_price and a crash for a zero one — the field is kept on the model purely for
    parity/display with the original tool.
    """
    raw = _A / ((rarity + _B) ** _C) + _D
    clamped = max(settings.min_price, min(settings.max_price, raw))
    return round(clamped)


def stat_bonus_percent(instance: "BallInstance", stat_modifiers: dict[int, int]) -> int:
    """Price bonus/malus from the card's stats, based on the average of attack_bonus and health_bonus."""
    avg = round((instance.attack_bonus + instance.health_bonus) / 2)
    avg = max(-40, min(40, avg))
    return stat_modifiers.get(avg, 0)


def special_bonus_percent(instance: "BallInstance", special_modifiers: dict[int, int]) -> int:
    """Price bonus/malus from the card's special, if any."""
    if not instance.special_id:
        return 0
    return special_modifiers.get(instance.special_id, 0)


def recommended_price(
    instance: "BallInstance",
    settings: "AuctionSettings",
    special_modifiers: dict[int, int],
    stat_modifiers: dict[int, int],
) -> int:
    """Suggested price shown to a seller listing a card for auction (includes the special bonus)."""
    value = base_value(instance.countryball.rarity, settings)
    value += value * stat_bonus_percent(instance, stat_modifiers) / 100
    value += value * special_bonus_percent(instance, special_modifiers) / 100
    return max(settings.min_price, round(value))


def direct_sale_price(
    instance: "BallInstance",
    settings: "AuctionSettings",
    stat_modifiers: dict[int, int],
    bonus_percent: int = 0,
) -> int:
    """
    Price the Hotel pays for a direct buyout. The caller is responsible for excluding
    special cards and excluded-rarity cards before calling this (specials can't be
    sold directly, so the special bonus never applies here). `bonus_percent` is the
    caller's best applicable AuctionBoosterRole.sell_bonus_percent, or 0.
    """
    value = base_value(instance.countryball.rarity, settings)
    value += value * stat_bonus_percent(instance, stat_modifiers) / 100
    if bonus_percent:
        value += value * bonus_percent / 100
    return max(settings.min_price, round(value))
