from django.apps import AppConfig


class AugmentAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "augment_app"
    verbose_name = "Augment Models"
    dpy_package = "augment_app.augment_ext"
