from typing import Iterable

from django.db import models
from django.core.exceptions import ValidationError

from bd_models.models import Ball, Player, Special

class CurrencySettings(models.Model):
    name = models.CharField(max_length=64)
    plural_name = models.CharField(max_length=64)
    emoji_id = models.BigIntegerField(help_text="Emoji id of the currency", null=True, blank=True)

    class Meta:
        managed = True
        db_table = "currencysettings"
    
    def __str__(self) -> str:
        return self.name

class Item(models.Model):
    name = models.CharField(max_length=64)
    description = models.TextField(
        null=True, blank=True, help_text="An optional description for the item"
    )
    prize = models.PositiveBigIntegerField(
        blank=True, 
        null=True, 
        help_text="The prize of the item. If blanks, it will free"
    )
    emoji_id = models.BigIntegerField(null=True, blank=False, help_text="Emoji Id of the item")
    minimum_rarity = models.FloatField(help_text="Minimum rarity range.", blank=True, null=True)
    maximum_rarity = models.FloatField(help_text="Maximum rarity range.", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    ball = models.ForeignKey(
        Ball, on_delete=models.SET_NULL, blank=True, null=True, help_text="A specific ball to give."
    )
    special = models.ForeignKey(
        Special, on_delete=models.SET_NULL, blank=True, null=True, help_text="The special of the item (optional)"
    )

    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: str | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        has_ball = self.ball is not None
        has_min = self.minimum_rarity is not None
        has_max = self.maximum_rarity is not None
        has_rarity = has_min or has_max

        if not has_ball and not has_rarity:
            raise ValidationError(
                "You must provide either a ball or a rarity range."
            )

        if has_ball and has_rarity:
            raise ValidationError(
                "You cannot set both a ball and a rarity range."
            )

        if has_rarity and not (has_min and has_max):
            raise ValidationError(
                "You must define both minimum and maximum rarity."
            )

        if has_min and has_max and self.minimum_rarity > self.maximum_rarity: # type: ignore
            raise ValidationError(
                "Minimum rarity cannot be greater than maximum rarity."
            )

        return super().save(force_insert, force_update, using, update_fields)

    class Meta:
        managed = True
        db_table = "item"

    def __str__(self) -> str:
        return self.name

class MoneyInstance(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE)
    amount = models.BigIntegerField(default=0)

    class Meta:
        managed = True
        db_table = "moneyinstance"

