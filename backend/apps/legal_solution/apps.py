from django.apps import AppConfig


class LegalSolutionConfig(AppConfig):
    name = "apps.legal_solution"
    verbose_name = "法律服务方案"

    def ready(self) -> None:
        from . import signals
