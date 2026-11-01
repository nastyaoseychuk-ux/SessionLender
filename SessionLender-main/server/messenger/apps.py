from django.apps import AppConfig


class MessengerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'messenger'

    def import_models(self):
        super().import_models()
        from . import desktop_models  # noqa: F401

    def ready(self):
        from . import signals, notifications  # noqa: F401
