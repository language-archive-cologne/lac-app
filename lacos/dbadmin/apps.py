from django.apps import AppConfig


class DbAdminConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lacos.dbadmin"
    verbose_name = "Database Admin"
