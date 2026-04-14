from django.db import models

from bd_models.models import Player

class PackResource(models.Model):
    player = models.OneToOneField(
        Player, 
        on_delete=models.CASCADE, 
        related_name="pack_resource"
    )
    uses = models.PositiveIntegerField(default=0)
    daily_cooldown = models.DateTimeField(null=True, blank=True)
    weekly_cooldown = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "packresource"
        managed = True