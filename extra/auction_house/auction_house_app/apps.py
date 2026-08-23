from django.apps import AppConfig


class AuctionHouseAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "auction_house_app"
    verbose_name = "Auction House Models"
    dpy_package = "auction_house_app.auction_house_ext"
