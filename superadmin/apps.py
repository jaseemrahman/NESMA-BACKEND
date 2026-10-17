from django.apps import AppConfig


class SuperadminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'superadmin'

    def ready(self):
        from superadmin import signals  # noqa: F401
