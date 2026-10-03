from django.apps import AppConfig


class LprConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lpr"
    verbose_name = "Placas e movimentações"

    def ready(self):
        from . import signals  # noqa: F401
