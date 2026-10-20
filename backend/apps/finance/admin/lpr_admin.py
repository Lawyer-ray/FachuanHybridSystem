"""LPR Admin配置.

提供LPR利率数据的管理界面，包含：
- LPR数据列表和编辑
- 手动同步按钮
- 计算器入口
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template.response import TemplateResponse
from django.urls import URLPattern, path

from apps.core.admin.base import BaseModelAdmin  # 解耦（2026-10-19）：不再跨 app 引 cases admin 的别名
from apps.finance.models.lpr_rate import LPRRate

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)


@admin.register(LPRRate)
class LPRRateAdmin(BaseModelAdmin):  # pragma: no cover
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
    list_per_page = 50
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

    def has_add_permission(self, request: HttpRequest) -> bool:  # pragma: no cover
        """禁止手动添加LPR数据."""
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
        """禁止修改LPR数据."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # pragma: no cover
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
            "元数据",
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

    def get_urls(self) -> list[URLPattern]:  # pragma: no cover
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
        return custom_urls + urls

    def changelist_view(
        self, request: HttpRequest, extra_context: dict | None = None
    ) -> TemplateResponse:  # pragma: no cover
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
            logger.warning("[LPRAdmin] Failed to get sync status: %s", e)
            extra_context["sync_status"] = None

        return super().changelist_view(request, extra_context=extra_context)  # type: ignore[return-value]

    def sync_view(self, request: HttpRequest) -> HttpResponse:  # pragma: no cover
        """同步LPR数据视图 - 直接执行同步."""
        from django.core.exceptions import PermissionDenied

        # 安全审计（2026-10-19）：状态变更只收 POST（GET 可被跨站 <img> 诱导触发刷资源）。
        # 权限校验用模型权限而非 has_change_permission——后者在本 Admin 被策略性写死
        # 返回 False（LPR 数据只读），用它把关会把同步这个唯一写入口也一并锁死（403）
        if request.method != "POST" or not request.user.has_perm("finance.change_lprrate"):
            raise PermissionDenied

        from apps.core.exceptions import BusinessException
        from apps.finance.services.lpr import LPRSyncService

        user: User = request.user
        logger.info("[LPRAdmin] User %s triggered sync from admin", user.id)

        try:
            service = LPRSyncService()
            result = service.sync_latest()

            self.message_user(
                request,
                "LPR数据同步成功：新增 %(created)s 条，更新 %(updated)s 条，跳过 %(skipped)s 条" % result,
            )
        except BusinessException as e:
            logger.error("[LPRAdmin] Sync failed: %s", e)
            self.message_user(request, f"同步失败: {e}", level="error")
        except Exception as e:
            logger.error("[LPRAdmin] Unexpected error during sync: %s", e)
            self.message_user(request, f"同步失败: {e!s}", level="error")

        return HttpResponseRedirect("../")

    def calculator_view(self, request: HttpRequest) -> TemplateResponse:  # pragma: no cover
        """LPR计算器视图."""
        from apps.finance.models.lpr_rate import LPRRate
        from apps.finance.services.lpr.rate_service import LPRRateService

        rate_service = LPRRateService()

        try:
            latest_rate = rate_service.get_latest_rate()
        except Exception:
            latest_rate = None

        context = {
            **self.admin_site.each_context(request),
            "title": "LPR利息计算器",
            "opts": self.model._meta,
            "recent_rates": LPRRate.objects.all()[:50],
            "latest_rate": latest_rate,
            "is_data_current": rate_service.is_data_current(),
            "sync_url": "sync/",
        }
        return render(request, "admin/finance/lpr/calculator.html", context)  # type: ignore[return-value]
