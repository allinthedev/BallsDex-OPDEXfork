from django.db import models

from bd_models.models import Player, Special

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
    minimum_rarity = models.FloatField(help_text="Minimum rarity range.")
    maximum_rarity = models.FloatField(help_text="Maximum rarity range.")
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    special = models.ForeignKey(
        Special, on_delete=models.SET_NULL, blank=True, null=True, help_text="The special of the item (optional)"
    )

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

