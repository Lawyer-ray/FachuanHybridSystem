"""Django admin configuration."""

import logging

from django.contrib import admin

logger = logging.getLogger(__name__)

try:
    import nested_admin

    BaseModelAdmin = nested_admin.NestedModelAdmin
    BaseStackedInline = nested_admin.NestedStackedInline
    BaseTabularInline = nested_admin.NestedTabularInline
except Exception:
    logger.exception("操作失败")

    BaseModelAdmin = admin.ModelAdmin
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
