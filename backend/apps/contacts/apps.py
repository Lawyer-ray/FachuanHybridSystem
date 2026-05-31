from __future__ import annotations

from django.apps import AppConfig

class ContactsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.contacts"
    verbose_name = "工作人员联系方式"
