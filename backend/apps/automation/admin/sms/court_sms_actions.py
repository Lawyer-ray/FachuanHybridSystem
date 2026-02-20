"""
法院短信 Admin 批量操作

提供短信批量处理、重试等操作功能.
"""

import logging
from typing import Any, cast

from django.contrib import messages
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("apps.automation")


def _get_court_sms_service() -> None:
    """获取法院短信服务实例(工厂函数)"""
    from apps.core.interfaces import ServiceLocator

    return ServiceLocator.get_court_sms_service()


class CourtSMSActionsMixin:
    """
    法院短信 Admin 批量操作混入类

    提供所有批量操作方法的实现.
    """

    def retry_processing_action(self, request: Any, queryset) -> None:
        """重新处理操作"""
        service = _get_court_sms_service()
        success_count = 0
        error_count = 0

        for sms in queryset:
            try:
                service.retry_processing(cast(int, sms.id))
                success_count += 1
                logger.info(f"管理员重新处理短信: SMS ID={sms.id}, User={request.user}")
            except Exception as e:
                error_count += 1
                logger.error(f"管理员重新处理短信失败: SMS ID={sms.id}, 错误: {e!s}")

        if success_count > 0:
            messages.success(request, f"成功重新处理 {success_count} 条短信")
        if error_count > 0:
            messages.error(request, f"重新处理失败 {error_count} 条短信")

    retry_processing_action.short_description = _("🔄 重新处理选中的短信")
