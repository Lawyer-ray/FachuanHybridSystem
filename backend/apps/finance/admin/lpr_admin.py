"""LPR Admin配置.

提供LPR利率数据的管理界面，包含：
- LPR数据列表和编辑
- 手动同步按钮
- 计算器入口
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import URLPattern, path
from django.utils.translation import gettext_lazy as _

from apps.cases.admin.base_admin import BaseModelAdmin
from apps.finance.models.lpr_rate import LPRRate

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


@admin.register(LPRRate)
class LPRRateAdmin(BaseModelAdmin):
    """LPR利率Admin配置.

    LPR数据只能通过同步获取，不允许手动添加/修改/删除。
    """

    list_display = (
        "effective_date",
        "rate_1y",
        "rate_5y",
        "is_auto_synced",
        "source",
        "updated_at",
    )
    list_filter = (
        "effective_date",
        "is_auto_synced",
    )
    search_fields = (
        "effective_date",
        "source",
    )
    ordering = ("-effective_date",)
    readonly_fields = (
        "effective_date",
        "rate_1y",
        "rate_5y",
        "source",
        "is_auto_synced",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """禁止手动添加LPR数据."""
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        """禁止修改LPR数据."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        """禁止删除LPR数据."""
        return False

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "effective_date",
                    "rate_1y",
                    "rate_5y",
                )
            },
        ),
        (
            _("元数据"),
            {
                "fields": (
                    "source",
                    "is_auto_synced",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_urls(self) -> list[URLPattern]:
        """添加自定义URL路由."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_view),
                name="finance_lprrate_sync",
            ),
            path(
                "calculator/",
                self.admin_site.admin_view(self.calculator_view),
                name="finance_lprrate_calculator",
            ),
        ]
        return custom_urls + urls  # type: ignore[no-any-return]

    def changelist_view(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> TemplateResponse:  # type: ignore[no-any-return]
        """列表页面视图，添加快捷操作按钮."""
        extra_context = extra_context or {}
        extra_context["sync_url"] = "sync/"
        extra_context["calculator_url"] = "calculator/"

        # 获取同步状态
        try:
            from apps.finance.services.lpr import LPRSyncService

            service = LPRSyncService()
            status = service.get_sync_status()
            extra_context["sync_status"] = status
        except Exception as e:
            logger.warning(f"[LPRAdmin] Failed to get sync status: {e}")
            extra_context["sync_status"] = None

        return super().changelist_view(request, extra_context=extra_context)  # type: ignore[no-any-return]

    def sync_view(self, request: HttpRequest) -> HttpResponse:
        """同步LPR数据视图 - 直接执行同步."""
        from apps.core.exceptions import BusinessException
        from apps.finance.services.lpr import LPRSyncService

        user: User = request.user
        logger.info(f"[LPRAdmin] User {user.id} triggered sync from admin")

        try:
            service = LPRSyncService()
            result = service.sync_latest()

            self.message_user(
                request,
                _("LPR数据同步成功：新增 %(created)s 条，更新 %(updated)s 条，跳过 %(skipped)s 条") % result,
            )
        except BusinessException as e:
            logger.error(f"[LPRAdmin] Sync failed: {e}")
            self.message_user(request, f"同步失败: {e}", level="error")
        except Exception as e:
            logger.error(f"[LPRAdmin] Unexpected error during sync: {e}")
            self.message_user(request, f"同步失败: {e!s}", level="error")

        return HttpResponseRedirect("../")

    def calculator_view(self, request: HttpRequest) -> TemplateResponse:
        """LPR计算器视图."""
        from apps.finance.models.lpr_rate import LPRRate

        # 获取最新的几条利率记录用于参考
        recent_rates = LPRRate.objects.all()[:10]

        context = {
            **self.admin_site.each_context(request),
            "title": _("LPR利息计算器"),
            "opts": self.model._meta,
            "recent_rates": recent_rates,
        }
        return render(request, "admin/finance/lpr/calculator.html", context)
