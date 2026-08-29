"""
Pure combat-resolution helpers for the Battle feature.

Kept independent of Discord/Django so the turn math can be read and adjusted in one place — the
cog owns the actual turn loop, persistence (serializing/deserializing BattleBall to/from
BattleSession.state) and Discord plumbing. Each function here takes plain values (already resolved
by the cog from the Matchup table, BattleSettings, etc.) and returns a small, renderable result.
"""

import random
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from battle_app.models import BattleSettings


class BattleAction(str, Enum):
    ATTACK = "attack"
    CRIT = "crit"
    HEAL = "heal"
    CAPACITY = "capacity"


@dataclass
class BattleBall:
    """One card's live state within a battle. JSON-serializable via `to_dict`/`from_dict`."""

    instance_id: int
    ball_id: int
    name: str
    owner_id: int
    health: int
    max_health: int
    attack: int
    rarity: float = 1.0
    emoji: str = ""
    capacity_name: str = ""
    capacity_logic: dict = field(default_factory=dict)
    dead: bool = False
    heal_uses: int = 0
    capacity_uses: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BattleBall":
        return cls(**data)


class ActionResult(NamedTuple):
    text: str
    damage: int = 0
    healed: int = 0
    crit: bool = False
    dodged: bool = False


def tier_scaling(attacker_rarity: float, defender_rarity: float, settings: "BattleSettings") -> tuple[float, float]:
    """
    Damage multiplier and bonus crit chance from the tier gap between attacker and defender.
    Tier = round(rarity); a LOWER rarity number is a rarer/stronger card, so a positive
    `tier_diff` means the defender is more common (an easier matchup) than the attacker.
    """
    tier_diff = round(defender_rarity) - round(attacker_rarity)
    if tier_diff >= 2:
        return settings.tier_enemy_2plus_lower_multiplier, settings.tier_enemy_2plus_lower_bonus_crit_chance
    if tier_diff == 1:
        return settings.tier_enemy_1_lower_multiplier, 0.0
    if tier_diff == 0:
        return settings.tier_same_multiplier, 0.0
    if tier_diff == -1:
        return settings.tier_enemy_1_higher_multiplier, 0.0
    return settings.tier_enemy_2plus_higher_multiplier, 0.0


def _damaging_action(
    action: BattleAction,
    attacker: BattleBall,
    defender: BattleBall,
    settings: "BattleSettings",
    matchup_multiplier: float,
    item_effect: tuple[str, float] | None,
) -> ActionResult:
    if random.random() < settings.dodge_chance:
        return ActionResult(text=f"**{defender.name}** dodges {attacker.name}'s attack!", dodged=True)

    tier_multiplier, tier_bonus_crit = tier_scaling(attacker.rarity, defender.rarity, settings)
    guaranteed_crit = item_effect is not None and item_effect[0] == "guaranteed_crit"

    if action is BattleAction.CRIT:
        crit = guaranteed_crit or (random.random() < settings.crit_chance + tier_bonus_crit)
        action_multiplier = settings.crit_multiplier if crit else settings.crit_fail_multiplier
    else:
        # A plain Attack has no baseline crit chance — only a favorable tier gap can trigger one.
        crit = guaranteed_crit or (tier_bonus_crit > 0 and random.random() < tier_bonus_crit)
        action_multiplier = settings.crit_multiplier if crit else 1.0

    if item_effect is not None and item_effect[0] == "attack_boost":
        action_multiplier *= item_effect[1]

    base = attacker.attack * random.uniform(settings.attack_variance_min, settings.attack_variance_max)
    damage = max(1, round(base * matchup_multiplier * tier_multiplier * action_multiplier))
    defender.health = max(0, defender.health - damage)
    if defender.health <= 0:
        defender.dead = True

    verb = "lands a **CRITICAL HIT** on" if crit else "hits"
    edge = " (lore advantage!)" if matchup_multiplier > 1.0 else ""
    text = f"**{attacker.name}** {verb} **{defender.name}** for **{damage}**{edge}"
    if defender.dead:
        text += f" — {defender.name} is defeated!"
    return ActionResult(text=text, damage=damage, crit=crit)


def _resolve_heal(
    attacker: BattleBall, settings: "BattleSettings", item_effect: tuple[str, float] | None
) -> ActionResult:
    if attacker.heal_uses >= settings.heal_uses_per_battle:
        return ActionResult(text=f"**{attacker.name}** has no more heals left this battle and attacks instead!")

    percent = random.uniform(settings.heal_percent_min, settings.heal_percent_max)
    if item_effect is not None and item_effect[0] == "extra_heal":
        percent += item_effect[1]

    missing = attacker.max_health - attacker.health
    healed = min(missing, round(attacker.max_health * percent / 100))
    attacker.health += healed
    attacker.heal_uses += 1
    return ActionResult(text=f"**{attacker.name}** heals for **{healed}** HP!", healed=healed)


def _resolve_capacity(
    attacker: BattleBall,
    defender: BattleBall,
    settings: "BattleSettings",
    matchup_multiplier: float,
    item_effect: tuple[str, float] | None,
) -> ActionResult:
    if attacker.capacity_uses >= settings.capacity_uses_per_battle:
        return ActionResult(text=f"**{attacker.name}** has already used its Capacity this battle and attacks instead!")

    attacker.capacity_uses += 1
    label = attacker.capacity_name or "Capacity"
    logic = attacker.capacity_logic or {}
    effect_type = logic.get("type")
    value = logic.get("value")

    if effect_type == "heal_percent" and isinstance(value, (int, float)):
        missing = attacker.max_health - attacker.health
        healed = min(missing, round(attacker.max_health * value / 100))
        attacker.health += healed
        return ActionResult(text=f"**{attacker.name}** uses **{label}** and heals for **{healed}** HP!", healed=healed)

    tier_multiplier, tier_bonus_crit = tier_scaling(attacker.rarity, defender.rarity, settings)

    if effect_type == "flat_damage" and isinstance(value, (int, float)):
        damage = max(1, round(value * matchup_multiplier * tier_multiplier))
        defender.health = max(0, defender.health - damage)
        if defender.health <= 0:
            defender.dead = True
        text = f"**{attacker.name}** unleashes **{label}** on **{defender.name}** for **{damage}**!"
        if defender.dead:
            text += f" — {defender.name} is defeated!"
        return ActionResult(text=text, damage=damage)

    multiplier = value if effect_type == "damage_multiplier" and isinstance(value, (int, float)) else None
    multiplier = multiplier or settings.default_capacity_multiplier
    if item_effect is not None and item_effect[0] == "attack_boost":
        multiplier *= item_effect[1]
    crit = tier_bonus_crit > 0 and random.random() < tier_bonus_crit
    if crit:
        multiplier *= settings.crit_multiplier

    base = attacker.attack * random.uniform(settings.attack_variance_min, settings.attack_variance_max)
    damage = max(1, round(base * matchup_multiplier * tier_multiplier * multiplier))
    defender.health = max(0, defender.health - damage)
    if defender.health <= 0:
        defender.dead = True
    text = f"**{attacker.name}** unleashes **{label}** on **{defender.name}** for **{damage}**!"
    if crit:
        text += "\n💥 **CRITICAL HIT!**"
    if defender.dead:
        text += f" — {defender.name} is defeated!"
    return ActionResult(text=text, damage=damage, crit=crit)


def resolve_action(
    action: BattleAction,
    attacker: BattleBall,
    defender: BattleBall,
    settings: "BattleSettings",
    matchup_multiplier: float = 1.0,
    item_effect: tuple[str, float] | None = None,
) -> ActionResult:
    """Resolve one turn's action, mutating `attacker`/`defender` health in place."""
    if action is BattleAction.HEAL:
        return _resolve_heal(attacker, settings, item_effect)
    if action is BattleAction.CAPACITY:
        return _resolve_capacity(attacker, defender, settings, matchup_multiplier, item_effect)
    return _damaging_action(action, attacker, defender, settings, matchup_multiplier, item_effect)


def hp_bar(current: int, maximum: int, length: int = 10) -> str:
    """A small unicode HP bar, e.g. '██████░░░░'."""
    if maximum <= 0:
        return "░" * length
    filled = round(length * max(0, current) / maximum)
    filled = min(length, max(0, filled))
    return "█" * filled + "░" * (length - filled)
