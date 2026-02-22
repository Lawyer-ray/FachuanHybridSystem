"""
合同显示服务

职责:
- 处理合同显示相关的业务逻辑
- 替代 Model 层的复杂 @property 方法
- 通过 ServiceLocator 获取跨模块服务
- 提供格式化的显示数据
- 使用缓存优化模板查询性能

Requirements: 1.1, 4.1, 4.2, 7.1, 8.1, 3.3, 10.3
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

from .contract_template_cache import ContractTemplateCache
from .wiring import get_document_service

if TYPE_CHECKING:
    from apps.contracts.models import Contract
    from apps.core.interfaces import IDocumentService

logger = logging.getLogger("apps.contracts")


class ContractDisplayService:
    """
    合同显示服务

    负责处理合同的格式化显示逻辑,包括:
    - 获取匹配的文书模板名称
    - 获取匹配的文件夹模板名称
    - 检查是否有匹配的模板
    - 批量获取模板信息(优化查询)
    - 使用 ContractTemplateCache 优化模板查询性能

    使用依赖注入模式,通过 ServiceLocator 获取跨模块服务.

    Example:
        >>> service = ContractDisplayService()
        >>> template_name = service.get_matched_document_template(contract)
        >>> folder_names = service.get_matched_folder_templates(contract)
        >>> has_templates = service.has_matched_templates(contract)
    """

    def __init__(
        self,
        document_service: IDocumentService | None = None,
        template_cache: ContractTemplateCache | None = None,
    ) -> None:
        """
        初始化合同显示服务

        Args:
            document_service: 文档服务实例(可选,用于依赖注入)
            template_cache: 模板缓存服务实例(可选,用于依赖注入)
        """
        self._document_service = document_service
        self._template_cache = template_cache

    @property
    def document_service(self) -> IDocumentService:
        """延迟加载文档服务"""
        if self._document_service is None:
            self._document_service = get_document_service()
        return self._document_service

    @property
    def template_cache(self) -> ContractTemplateCache:
        """延迟加载模板缓存服务"""
        if self._template_cache is None:
            self._template_cache = ContractTemplateCache()
        return self._template_cache

    def clear_cache_for_case_type(self, case_type: str) -> None:
        """清除特定案件类型的所有缓存"""
        self.template_cache.clear_cache_for_case_type(case_type)

    def clear_all_cache(self) -> None:
        """清除所有模板缓存"""
        self.template_cache.clear_all_cache()

    def get_matched_document_template(self, contract: Contract) -> str:
        """获取匹配的文书模板名称"""
        try:
            # 尝试从缓存获取
            templates = self.template_cache.get_document_templates(contract.case_type)

            if templates is not None:
                logger.debug("从缓存获取合同 %s 的文书模板", contract.pk)
            else:
                # 缓存未命中,从数据库查询
                templates = self.document_service.find_matching_contract_templates(contract.case_type)
                # 缓存查询结果
                self.template_cache.set_document_templates(contract.case_type, templates)

            if not templates:
                logger.debug("合同 %s (%s) 无匹配的文书模板", contract.pk, contract.case_type)
                return _("无匹配模板")

            # 格式化显示文本
            template_displays = []
            for template in templates:
                type_display = template.get("type_display", "")
                name = template.get("name", "")
                if type_display:
                    template_displays.append(f"{name}（{type_display}）")
                else:
                    template_displays.append(name)

            result = "、".join(template_displays)
            logger.debug("合同 %s 匹配的文书模板: %s", contract.pk, result)
            return result

        except Exception as e:
            logger.error("查询合同 %s 的文书模板失败: %s", contract.pk, e, exc_info=True)
            return _("查询失败")

    def get_matched_folder_templates(self, contract: Contract) -> str:
        """获取匹配的文件夹模板名称"""
        try:
            # 尝试从缓存获取
            templates = self.template_cache.get_folder_templates(contract.case_type)

            if templates is not None:
                logger.debug("从缓存获取合同 %s 的文件夹模板", contract.pk)
            else:
                # 缓存未命中,从数据库查询
                templates = self.document_service.find_matching_folder_templates(
                    template_type="contract", case_type=contract.case_type
                )
                # 缓存查询结果
                self.template_cache.set_folder_templates(contract.case_type, templates)

            if not templates:
                logger.debug("合同 %s (%s) 无匹配的文件夹模板", contract.pk, contract.case_type)
                return _("无匹配模板")

            # 提取模板名称并用顿号连接
            template_names = [template.get("name", "") for template in templates]
            result = "、".join(template_names)

            logger.debug("合同 %s 匹配的文件夹模板: %s", contract.pk, result)
            return result

        except Exception as e:
            logger.error("查询合同 %s 的文件夹模板失败: %s", contract.pk, e, exc_info=True)
            return _("查询失败")

    def has_matched_templates(self, contract: Contract) -> bool:
        """检查是否有匹配的模板"""
        try:
            # 尝试从缓存获取
            result = self.template_cache.get_template_check(contract.case_type)

            if result is not None:
                logger.debug("从缓存获取合同 %s 的模板检查结果", contract.pk)
            else:
                # 缓存未命中,从数据库查询
                result = self.document_service.check_has_matching_templates(contract.case_type)
                # 缓存查询结果
                self.template_cache.set_template_check(contract.case_type, result)

            has_folder = result.get("has_folder", False)
            has_document = result.get("has_document", False)

            # 只有同时有文件夹模板和文书模板才返回 True
            has_both = has_folder and has_document

            logger.debug(
                "合同 %s 模板检查: 文件夹=%s, 文书=%s, 结果=%s",
                contract.pk, has_folder, has_document, has_both,
            )
            return has_both

        except Exception as e:
            logger.error("检查合同 %s 的模板失败: %s", contract.pk, e, exc_info=True)
            return False

    def batch_get_template_info(self, contracts: list[Contract]) -> dict[int, dict[str, Any]]:
        """批量获取合同的模板信息"""
        result = {}
        if not contracts:
            return result

        try:
            case_types = set(contract.case_type for contract in contracts)
            template_cache: dict[str, dict[str, Any]] = {}

            logger.debug("批量查询开始: %d 个合同,%d 种案件类型", len(contracts), len(case_types))

            for case_type in case_types:
                template_cache[case_type] = self._fetch_template_info_for_case_type(case_type)

            for contract in contracts:
                result[contract.id] = template_cache.get(
                    contract.case_type,
                    {"document_template": _("查询失败"), "folder_template": _("查询失败"), "has_templates": False},
                )

            logger.info("批量获取 %d 个合同的模板信息完成,涉及 %d 种案件类型", len(contracts), len(case_types))

        except Exception as e:
            logger.error("批量获取模板信息失败: %s", e, exc_info=True)
            for contract in contracts:
                result[contract.id] = {
                    "document_template": _("查询失败"),
                    "folder_template": _("查询失败"),
                    "has_templates": False,
                }

        return result

    def _fetch_template_info_for_case_type(self, case_type: str) -> dict[str, Any]:
        """获取单个案件类型的模板信息"""
        try:
            doc_templates = self.template_cache.get_document_templates(case_type)
            if doc_templates is None:
                doc_templates = self.document_service.find_matching_contract_templates(case_type)
                self.template_cache.set_document_templates(case_type, doc_templates)

            folder_templates = self.template_cache.get_folder_templates(case_type)
            if folder_templates is None:
                folder_templates = self.document_service.find_matching_folder_templates(
                    template_type="contract", case_type=case_type
                )
                self.template_cache.set_folder_templates(case_type, folder_templates)

            check_result = self.template_cache.get_template_check(case_type)
            if check_result is None:
                check_result = self.document_service.check_has_matching_templates(case_type)
                self.template_cache.set_template_check(case_type, check_result)

            return {
                "document_template": self._format_doc_templates(doc_templates),
                "folder_template": self._format_folder_templates(folder_templates),
                "has_templates": check_result.get("has_folder", False) and check_result.get("has_document", False),
            }
        except Exception as e:
            logger.error("批量查询案件类型 %s 的模板失败: %s", case_type, e, exc_info=True)
            return {"document_template": _("查询失败"), "folder_template": _("查询失败"), "has_templates": False}

    def _format_doc_templates(self, doc_templates: list[dict[str, Any]]) -> str:
        if not doc_templates:
            return _("无匹配模板")
        displays = []
        for t in doc_templates:
            type_display = t.get("type_display", "")
            name = t.get("name", "")
            displays.append(f"{name}（{type_display}）" if type_display else name)
        return "、".join(displays)

    def _format_folder_templates(self, folder_templates: list[dict[str, Any]]) -> str:
        if not folder_templates:
            return _("无匹配模板")
        return "、".join(t.get("name", "") for t in folder_templates)
