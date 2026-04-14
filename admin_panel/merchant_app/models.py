from django.db import models

from bd_models.models import Ball, Player, Special

class MerchantSettings(models.Model):
    rotation = models.PositiveIntegerField(
        help_text="Duration of the items in minutes. Default to 24 hours.", default=1440
    )
    items = models.PositiveBigIntegerField(
        help_text="How many items will be in the store. Default to 3 items.", default=3
    )
    
    class Meta:
        managed = True
        db_table = "merchantsettings"

    def __str__(self) -> str:
        return "Merchant Settings"


class MerchantItem(models.Model):
    name = models.CharField(unique=True, max_length=64)
    prize = models.PositiveIntegerField(null=True, blank=True)
    start_date = models.DateTimeField(
        help_text="Start time of the item. If blank, starts immediately", null=True, blank=True
    )
    end_date = models.DateTimeField(
        help_text="End time of the item. If blank, the item is permanent", null=True, blank=True
    )
    rarity = models.FloatField(help_text="Value between 0 and 1, determine if a item is rarest than other")
    ball = models.ForeignKey(Ball, on_delete=models.CASCADE)
    special = models.ForeignKey(Special, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(editable=False, auto_now_add=True)

    def __str__(self) -> str:
        return self.name

    class Meta:
        managed = True
        db_table = "merchantitem"


class MerchantInstance(models.Model):
    player = models.OneToOneField(Player, on_delete=models.CASCADE, related_name="merchant")
    items = models.ManyToManyField(MerchantItem, blank=True)
    rotation_ends_at = models.DateTimeField()

    class Meta:
        managed = True
        db_table = "merchantinstance"

class GlobalShop(models.Model):
    name = models.CharField(max_length=64, unique=True)
    banner = models.ImageField(null=True, blank=True, help_text="An optional promotional banner for this shop.")
    items = models.ManyToManyField(MerchantItem, blank=True)

    class Meta:
        managed = True
        db_table = "globalshop"
