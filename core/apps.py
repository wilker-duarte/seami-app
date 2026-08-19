from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Núcleo do Sistema SEAMI'

    def ready(self):
        try:
            from django.contrib import admin
            from .admin_export import export_as_csv_action, export_as_json_action
            admin.site.add_action(export_as_csv_action, 'export_as_csv')
            admin.site.add_action(export_as_json_action, 'export_as_json')
        except Exception:
            pass

