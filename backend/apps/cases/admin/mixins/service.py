from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.cases.services.case_admin_service import CaseAdminService
    from apps.cases.services.case_chat_service import CaseChatService


class CaseAdminServiceMixin:
    """Admin 层服务工厂 mixin，统一提供 Service 实例获取方法。"""

    def _get_case_admin_service(self) -> CaseAdminService:
        """工厂方法：获取 CaseAdminService 实例（延迟导入避免循环依赖）。"""
        from apps.cases.services.case_admin_service import CaseAdminService

        return CaseAdminService()

    def _get_case_chat_service(self) -> CaseChatService:
        """工厂方法：获取 CaseChatService 实例（延迟导入避免循环依赖）。"""
        from apps.cases.services.case_chat_service import CaseChatService

        return CaseChatService()

    def _get_case_material_service(self) -> Any:
        """工厂方法：获取 CaseMaterialService 实例（延迟导入避免循环依赖）。"""
        from apps.cases.services.material.wiring import build_case_material_service

        return build_case_material_service()

    def _get_case_template_binding_service(self) -> Any:
        """工厂方法：获取 CaseTemplateBindingService 实例（延迟导入避免循环依赖）。"""
        from apps.cases.services.template.case_template_binding_service import CaseTemplateBindingService
        from apps.core.interfaces import ServiceLocator

        return CaseTemplateBindingService(document_service=ServiceLocator.get_document_service())
