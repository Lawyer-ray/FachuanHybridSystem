"""
Contract Admin - Display Format Mixin

只读显示方法：名称链接、律师信息、模板匹配等.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import BusinessException

if TYPE_CHECKING:
    from django.db.models import Model

logger = logging.getLogger("apps.contracts")


def _get_contract_display_service() -> Any:
    """工厂函数获取合同显示服务"""
    from apps.contracts.admin.wiring_admin import get_contract_display_service

    return get_contract_display_service()


class ContractDisplayFormatMixin:
    """合同 Admin 只读显示方法的 Mixin"""

    if TYPE_CHECKING:
        model: type[Model]

    @admin.display(description=_("合同名称"), ordering="name")
    def name_link(self, obj: Any) -> Any:
        """生成指向详情页的合同名称链接"""
        url = reverse("admin:contracts_contract_detail", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.name)

    @admin.display(description=_("主办律师"))
    def get_primary_lawyer(self, obj: Any) -> Any:
        """显示主办律师（使用 prefetch_related 数据避免 N+1）"""
        for assignment in obj.assignments.all():
            if assignment.is_primary:
                lawyer = assignment.lawyer
                return lawyer.real_name or lawyer.username
        return "-"

    def _get_primary_lawyer_obj(self, obj: Any) -> Any:
        """返回主办律师对象（供详情页模板使用）"""
        for assignment in obj.assignments.all():
            if assignment.is_primary:
                return assignment.lawyer
        return None

    @admin.display(description=_("主办律师"))
    def get_primary_lawyer_display(self, obj: Any) -> Any:
        """详情页显示主办律师(只读)"""
        from apps.contracts.admin.wiring_admin import get_contract_assignment_query_service

        service = get_contract_assignment_query_service()
        assignment = service.get_primary_lawyer(obj.pk)
        if assignment:
            lawyer = assignment.lawyer
            name = lawyer.real_name or lawyer.username
            return f"{name} (ID: {lawyer.id})"
        return _("无")

    @admin.display(description=_("律所OA链接"))
    def law_firm_oa_link_display(self, obj: Any) -> Any:
        """显示合同所属律所的 OA 登录链接（可点击）。"""
        from apps.oa_filing.services.script_executor_service import SUPPORTED_SITES
        from apps.organization.models import AccountCredential

        law_firm_ids: list[int] = []
        seen: set[int] = set()
        for assignment in obj.assignments.select_related("lawyer").all():
            lawyer = getattr(assignment, "lawyer", None)
            law_firm_id = getattr(lawyer, "law_firm_id", None)
            if not law_firm_id or law_firm_id in seen:
                continue
            seen.add(int(law_firm_id))
            law_firm_ids.append(int(law_firm_id))

        if not law_firm_ids:
            return _("未配置")

        credential = (
            AccountCredential.objects.filter(
                lawyer__law_firm_id__in=law_firm_ids,
                site_name__in=SUPPORTED_SITES,
            )
            .exclude(url__isnull=True)
            .exclude(url="")
            .order_by("id")
            .first()
        )

        if not credential:
            return _("未配置")

        return format_html(
            '<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>',
            credential.url,
            _("打开OA系统"),
        )

    @admin.display(description=_("建档编号"))
    def filing_number_display(self, obj: Any) -> Any:
        """显示建档编号(只读)

        如果合同已有建档编号,显示编号;否则显示"未生成".

        Requirements: 1.1, 1.2, 3.1
        """
        if obj and obj.filing_number:
            return obj.filing_number
        return _("未生成")

    @admin.display(description=_("匹配的合同模板"))
    def get_matched_template_display(self, obj: Any) -> Any:
        """显示匹配的合同模板

        Requirements: 1.4
        """
        if not obj or not obj.pk:
            return _("请先保存合同")

        try:
            display_service = _get_contract_display_service()
            return display_service.get_matched_document_template(obj)
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("获取合同 %s 匹配模板失败: %s", obj.id, e, exc_info=True)
            return _("查询失败")

    @admin.display(description=_("匹配的文件夹模板"))
    def get_matched_folder_templates_display(self, obj: Any) -> Any:
        """显示匹配的文件夹模板

        Requirements: 7.1
        """
        if not obj or not obj.pk:
            return _("请先保存合同")

        try:
            display_service = _get_contract_display_service()
            return display_service.get_matched_folder_templates(obj)
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("获取合同 %s 匹配文件夹模板失败: %s", obj.id, e, exc_info=True)
            return _("查询失败")
