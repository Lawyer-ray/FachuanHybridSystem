"""
Contract Admin - Display Mixin

显示相关的方法:详情页视图、字段显示等.
"""


from __future__ import annotations

import logging
from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import BusinessException, NotFoundError

logger = logging.getLogger("apps.contracts")


def _get_contract_admin_service() -> Any:
    """工厂函数获取合同 Admin 服务"""
    from apps.contracts.admin.wiring_admin import get_contract_admin_service

    return get_contract_admin_service()


def _get_contract_display_service() -> Any:
    """工厂函数获取合同显示服务"""
    from apps.contracts.admin.wiring_admin import get_contract_display_service

    return get_contract_display_service()


class ContractDisplayMixin:
    """合同 Admin 显示相关方法的 Mixin"""

    @admin.display(description=_("合同名称"), ordering="name")
    def name_link(self, obj) -> Any:
        """生成指向详情页的合同名称链接"""
        url = reverse("admin:contracts_contract_detail", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.name)

    @admin.display(description=_("主办律师"))
    def get_primary_lawyer(self, obj) -> Any:
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
    def get_primary_lawyer_display(self, obj) -> Any:
        """详情页显示主办律师(只读)"""
        from apps.contracts.admin.wiring_admin import get_contract_assignment_query_service

        service = get_contract_assignment_query_service()
        assignment = service.get_primary_lawyer(obj.pk)
        if assignment:
            lawyer = assignment.lawyer
            name = lawyer.real_name or lawyer.username
            return f"{name} (ID: {lawyer.id})"
        return _("无")

    @admin.display(description=_("建档编号"))
    def filing_number_display(self, obj) -> Any:
        """显示建档编号(只读)

        如果合同已有建档编号,显示编号;否则显示"未生成".

        Requirements: 1.1, 1.2, 3.1
        """
        if obj and obj.filing_number:
            return obj.filing_number
        return _("未生成")

    @admin.display(description=_("匹配的合同模板"))
    def get_matched_template_display(self, obj) -> Any:
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
    def get_matched_folder_templates_display(self, obj) -> Any:
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

    def get_urls(self) -> Any:
        """添加自定义 URL 路由"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:object_id>/detail/",
                self.admin_site.admin_view(self.detail_view),
                name="contracts_contract_detail",
            ),
        ]
        return custom_urls + urls

    def detail_view(self, request, object_id) -> Any:
        """合同详情页视图"""
        # 权限检查
        if not self.has_view_permission(request):
            raise PermissionDenied

        # 获取合同对象,优化查询
        admin_service = _get_contract_admin_service()
        try:
            contract = admin_service.query_service.get_contract_detail(object_id)
        except NotFoundError:
            raise Http404(_("合同不存在")) from None

        # 判断是否显示代理阶段(仅民商事/刑事/行政/劳动仲裁类型显示)
        ctx_data = admin_service.get_contract_detail_context(contract.id)

        # 构建上下文
        context = self.admin_site.each_context(request)
        context.update(
            {
                "contract": contract,
                "title": _("合同详情: %(name)s") % {"name": contract.name},
                "opts": self.model._meta,
                "has_change_permission": self.has_change_permission(request, contract),
                "has_view_permission": self.has_view_permission(request, contract),
                # 传递模板需要的额外数据
                "primary_lawyer": self._get_primary_lawyer_obj(contract),
                "contract_parties": contract.contract_parties.all(),
                "assignments": contract.assignments.all(),
                "payments": ctx_data["payments"],
                "total_payment_amount": ctx_data["total_payment_amount"],
                "reminders": contract.reminders.all().order_by("due_at"),
                "supplementary_agreements": ctx_data["supplementary_agreements"],
                "folder_binding": getattr(contract, "folder_binding", None),
                "show_representation_stages": ctx_data["show_representation_stages"],
                "representation_stages_display": ctx_data["representation_stages_display"],
                "today": ctx_data["today"],
                "soon_due_date": ctx_data["soon_due_date"],
                "has_contract_template": ctx_data["has_contract_template"],
                "has_folder_template": ctx_data["has_folder_template"],
                "has_supplementary_agreements": ctx_data["has_supplementary_agreements"],
                "payment_progress": ctx_data["payment_progress"],
                "invoice_summary": ctx_data["invoice_summary"],
                "related_cases": ctx_data["related_cases"],
            }
        )

        return render(request, "admin/contracts/contract/detail.html", context)

    def _check_contract_template(self, contract) -> Any:
        """
        检查是否有匹配的合同模板

        使用 ContractDisplayService 检查模板,避免直接导入 documents 模块.
        添加错误处理,确保在查询失败时返回 False.

        Requirements: 1.4, 6.2
        """
        try:
            display_service = _get_contract_display_service()
            result = display_service.get_matched_document_template(contract)
            return result not in ["无匹配模板", "查询失败"]
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("检查合同 %s 的文书模板失败: %s", contract.id, e, exc_info=True)
            return False

    def _check_folder_template(self, contract) -> Any:
        """
        检查是否有匹配的文件夹模板

        使用 ContractDisplayService 检查模板,避免直接导入 documents 模块.
        添加错误处理,确保在查询失败时返回 False.

        Requirements: 1.4, 6.2
        """
        try:
            display_service = _get_contract_display_service()
            result = display_service.get_matched_folder_templates(contract)
            return result not in ["无匹配模板", "查询失败"]
        except (BusinessException, RuntimeError, Exception) as e:
            logger.error("检查合同 %s 的文件夹模板失败: %s", contract.id, e, exc_info=True)
            return False
