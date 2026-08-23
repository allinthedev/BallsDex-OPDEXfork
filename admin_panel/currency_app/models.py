from typing import Iterable

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.db import models

from bd_models.models import Ball, Player, Special, balls


class CurrencySettings(models.Model):
    spawn_chance = models.FloatField(default=0.2, help_text="Value between 0 and 1, chances to spawn currency.")
    spawn_amount = models.PositiveIntegerField(default=500, help_text="The amount of currency to give from a spawn.")

    base_daily_amount = models.PositiveIntegerField(
        default=1500, help_text="Flat amount claimed by /daily every time, on top of the streak bonus."
    )
    day1_reward = models.PositiveIntegerField(default=100, help_text="/daily reward on streak day 1.")
    day2_reward = models.PositiveIntegerField(default=200, help_text="/daily reward on streak day 2.")
    day3_reward = models.PositiveIntegerField(default=300, help_text="/daily reward on streak day 3.")
    day4_reward = models.PositiveIntegerField(default=400, help_text="/daily reward on streak day 4.")
    day5_reward = models.PositiveIntegerField(default=500, help_text="/daily reward on streak day 5.")
    day6_reward = models.PositiveIntegerField(default=600, help_text="/daily reward on streak day 6.")
    day7_reward = models.PositiveIntegerField(default=1000, help_text="/daily reward on streak day 7.")
    streak_grace_hours = models.PositiveIntegerField(
        default=48,
        help_text="A player must claim /daily again within this many hours of their last claim to keep "
        "their streak going. Past this window, the streak resets to day 1.",
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
        db_table = "currencysettings"

    def __str__(self) -> str:
        return "Currency Settings"


class DailyBonusServer(models.Model):
    """
    One row per Discord server. Add role/bonus pairs to it via the inline "+" on this
    object's admin page — a server can have several roles, each with its own bonus.
    """

    server_id = models.BigIntegerField(unique=True, help_text="Discord server ID this configuration applies to.")

    roles: models.QuerySet["DailyBonusRole"]

    class Meta:
        managed = True
        db_table = "dailybonusserver"

    def __str__(self) -> str:
        return f"Daily bonus config for {self.server_id}"


class DailyBonusRole(models.Model):
    """A role granting a flat /daily bonus. If a player has several, the highest applies."""

    server = models.ForeignKey(DailyBonusServer, on_delete=models.CASCADE, related_name="roles")
    role_id = models.BigIntegerField(help_text="Role ID granting the flat /daily bonus.")
    bonus_amount = models.PositiveIntegerField(default=500, help_text="Flat bonus added to every /daily claim.")

    class Meta:
        managed = True
        db_table = "dailybonusrole"
        unique_together = (("server", "role_id"),)

    def __str__(self) -> str:
        return f"Role {self.role_id} (+{self.bonus_amount})"


class Item(models.Model):
    name = models.CharField(max_length=64)
    description = models.TextField(null=True, blank=True, help_text="An optional description for the item")
    prize = models.PositiveBigIntegerField(
        blank=True, null=True, help_text="The prize of the item. If blanks, it will free"
    )
    emoji_id = models.BigIntegerField(null=True, blank=False, help_text="Emoji Id of the item")
    minimum_rarity = models.FloatField(help_text="Minimum rarity range.", blank=True, null=True)
    maximum_rarity = models.FloatField(help_text="Maximum rarity range.", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    special = models.ForeignKey(
        Special, on_delete=models.SET_NULL, blank=True, null=True, help_text="The special of the item (optional)"
    )
    balls: models.QuerySet["ItemBall"]

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_min = self.minimum_rarity is not None
        has_max = self.maximum_rarity is not None
        has_rarity = has_min or has_max

        if has_rarity and not (has_min and has_max):
            raise ValidationError("You must define both minimum and maximum rarity.")

        if has_min and has_max and self.minimum_rarity > self.maximum_rarity:  # type: ignore
            raise ValidationError("Minimum rarity cannot be greater than maximum rarity.")

        return super().save(
            force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields
        )

    class Meta:
        managed = True
        db_table = "item"

    def __str__(self) -> str:
        return self.name


class ItemBall(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="balls")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE)
    ball_id: int

    @property
    def cached_ball(self) -> Ball:
        return balls.get(self.ball_id) or self.ball

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_rarity = self.item.minimum_rarity and self.item.maximum_rarity
        if has_rarity:
            raise ValidationError("You must define null `minimum_rarity` and `maximum_rarity` in the original item.")

        return super().save(
            force_insert=force_insert, force_update=force_update, using=using, update_fields=update_fields
        )

    class Meta:
        managed = True
        db_table = "itemball"
