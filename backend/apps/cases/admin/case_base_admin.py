"""Django admin configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib import admin

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    BaseModelAdmin = admin.ModelAdmin
    BaseStackedInline = admin.StackedInline
    BaseTabularInline = admin.TabularInline
else:
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
