from typing import TypedDict
from enum import StrEnum

class ItemType(StrEnum):
    Weapon = "weapon"
    Crew = "crew"
    Fruit = "fruit"
    Ship = "ship"

class Item(TypedDict):
    name: str
    rarity: int
    type: ItemType