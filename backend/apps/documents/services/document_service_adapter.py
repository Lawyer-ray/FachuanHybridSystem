"""Business logic services."""

from __future__ import annotations

import logging

"""
文档服务适配器

实现 IDocumentService 接口,供其他模块(如合同模块、案件模块)调用.
使用延迟导入避免循环依赖.

Requirements: 2.1, 2.2, 4.4, 6.1, 6.2, 7.1
"""

from typing import TYPE_CHECKING, Any, cast

from apps.core.dtos import DocumentTemplateDTO

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DocumentServiceAdapter:
    """
    文档服务适配器

    实现 IDocumentService 接口,提供文档模块的核心功能给其他模块使用.
    使用延迟导入避免循环依赖问题.

    Requirements: 2.1, 2.2, 5.5, 6.1, 6.2
    """

    def __init__(
        self,
        template_query_service: Any | None = None,
        template_matching_service: Any | None = None,
        template_binding_service: Any | None = None,
    ) -> None:
        self._template_query_service = template_query_service
        self._template_matching_service = template_matching_service
        self._template_binding_service = template_binding_service

    @property
    def template_query_service(self) -> Any:
        if self._template_query_service is None:
            from apps.documents.services.document_template_query_service import DocumentTemplateQueryService

            self._template_query_service = DocumentTemplateQueryService()
        return self._template_query_service

    @property
    def template_matching_service(self) -> Any:
        if self._template_matching_service is None:
            from apps.documents.services.template_matching_service import TemplateMatchingService

            self._template_matching_service = TemplateMatchingService()
        return self._template_matching_service

    @property
    def template_binding_service(self) -> Any:
        if self._template_binding_service is None:
            from apps.documents.services.contract_template_binding_service import DocumentTemplateBindingService

            self._template_binding_service = DocumentTemplateBindingService()
        return self._template_binding_service

    def get_matched_document_templates(self, case_type: str) -> str:
        """
        获取匹配的文书模板名称

        根据案件类型查找适用的文书模板,返回模板名称字符串.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            模板名称字符串,多个模板用"、"分隔.
            如果没有匹配返回 "无匹配模板"

        Requirements: 5.1, 5.5
        """
        try:
            matched_templates = self.template_matching_service.find_matching_case_document_template_names(case_type)
            from apps.documents.presenters.template_names_presenter import format_template_names

            return format_template_names(matched_templates)
        except Exception as e:
            logger.error("获取文书模板失败,案件类型: %s,错误: %s", case_type, e)
            return "查询失败"

    def get_matched_folder_templates(self, case_type: str) -> str:
        """
        获取匹配的文件夹模板名称

        根据案件类型查找适用的文件夹模板,返回模板名称字符串.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            模板名称字符串,多个模板用"、"分隔.
            如果没有匹配返回 "无匹配模板"

        Requirements: 5.2, 5.5
        """
        return self.get_matched_folder_templates_with_legal_status(case_type, [])

    def get_matched_folder_templates_with_legal_status(self, case_type: str, legal_statuses: list[str]) -> str:
        """
        获取匹配的文件夹模板名称(支持诉讼地位匹配)

        根据案件类型和诉讼地位查找适用的文件夹模板,返回模板名称字符串.
        匹配逻辑:
        1. 首先匹配案件类型
        2. 然后根据模板的 legal_status_match_mode 匹配诉讼地位:
           - any: 模板的诉讼地位列表为空,或案件诉讼地位与模板诉讼地位有交集
           - all: 案件诉讼地位包含模板的所有诉讼地位
           - exact: 案件诉讼地位与模板诉讼地位完全一致

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')
            legal_statuses: 案件的诉讼地位列表(我方当事人的诉讼地位)

        Returns:
            模板名称字符串,多个模板用"、"分隔.
            如果没有匹配返回 "无匹配模板"

        Requirements: 5.2, 5.5
        """
        try:
            matched_templates = (
                self.template_matching_service.find_matching_case_folder_template_names_with_legal_status(
                    case_type, legal_statuses
                )
            )
            from apps.documents.presenters.template_names_presenter import format_template_names

            return format_template_names(matched_templates)
        except Exception:
            logger.exception(
                "get_matched_folder_templates_failed", extra={"case_type": case_type, "legal_statuses": legal_statuses}
            )
            return "查询失败"

    def get_folder_binding_path(self, case_type: str, subdir_key: str) -> Any:
        """
        获取文书模板绑定配置的文件夹路径

        根据案件类型和子目录键名查找配置的文件夹路径.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')
            subdir_key: 子目录键名(如 'case_documents')

        Returns:
            配置的子目录路径,如 "1-律师资料/2-案件文书"
            如果没有配置则返回 None

        Requirements: 5.4, 5.5
        """
        try:
            return self.template_binding_service.get_case_subdir_path_internal(
                case_type=case_type, subdir_key=subdir_key
            )
        except Exception:
            logger.exception("get_folder_binding_path_failed", extra={"case_type": case_type, "subdir_key": subdir_key})
            raise

    def find_matching_case_file_templates(self, case_type: str, case_stage: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            self.template_matching_service.find_matching_case_file_templates(case_type, case_stage),
        )

    def find_matching_contract_templates(self, case_type: str) -> list[dict[str, Any]]:
        """
        查找匹配的合同文书模板

        根据案件类型查找适用的文书模板,返回模板的基本信息.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            模板信息列表,每个元素包含:
            - id: 模板 ID
            - name: 模板名称
            - type_display: 模板类型显示名称(如 "委托代理合同")

        Raises:
            ValidationException: 案件类型无效
        """
        return cast(list[dict[str, Any]], self.template_matching_service.find_matching_contract_templates(case_type))

    def find_matching_folder_templates(self, template_type: str, case_type: str | None = None) -> list[dict[str, Any]]:
        """
        查找匹配的文件夹模板

        根据模板类型和案件类型查找适用的文件夹模板.

        Args:
            template_type: 模板类型('contract' 或 'case')
            case_type: 案件类型(可选,如 'civil', 'criminal')

        Returns:
            模板信息列表,每个元素包含:
            - id: 模板 ID
            - name: 模板名称

        Raises:
            ValidationException: 模板类型无效
        """
        return cast(
            list[dict[str, Any]],
            self.template_matching_service.find_matching_folder_templates(template_type, case_type),
        )

    def check_has_matching_templates(self, case_type: str) -> dict[str, bool]:
        """
        检查是否有匹配的模板

        检查指定案件类型是否同时有文件夹模板和文书模板.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            包含检查结果的字典:
            - has_folder: 是否有匹配的文件夹模板
            - has_document: 是否有匹配的文书模板

        Raises:
            ValidationException: 案件类型无效
        """
        return cast(dict[str, bool], self.template_matching_service.check_has_matching_templates(case_type))

    # ============================================================
    # 内部方法 - 供跨模块调用(无权限检查)
    # Requirements: 4.4, 7.1
    # ============================================================

    def get_template_by_id_internal(self, template_id: int) -> DocumentTemplateDTO | None:
        """
        内部方法:根据 ID 获取文档模板

        Args:
            template_id: 模板 ID

        Returns:
            DocumentTemplateDTO,不存在返回 None

        Requirements: 7.1, 4.4
        """
        return self.template_query_service.get_template_by_id_internal(template_id) # type: ignore

    def get_template_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> DocumentTemplateDTO | None:
        """
        内部方法:根据功能代码获取文档模板

        Args:
            function_code: 功能代码
            case_type: 案件类型(可选)
            is_active: 是否只查询活跃模板

        Returns:
            DocumentTemplateDTO,不存在返回 None

        Requirements: 7.1, 4.4
        """
        return self.template_query_service.get_template_by_function_code_internal( # type: ignore
            function_code, case_type=case_type, is_active=is_active
        )

    def list_templates_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> list[DocumentTemplateDTO]:
        """
        内部方法:根据功能代码获取模板列表

        Args:
            function_code: 功能代码
            case_type: 案件类型(可选)
            is_active: 是否只查询活跃模板

        Returns:
            DocumentTemplateDTO 列表

        Requirements: 7.1, 4.4
        """
        return cast(
            list[DocumentTemplateDTO],
            self.template_query_service.list_templates_by_function_code_internal(
                function_code, case_type=case_type, is_active=is_active
            ),
        )

    def get_templates_by_case_type_internal(self, case_type: str, is_active: bool = True) -> list[DocumentTemplateDTO]:
        """
        内部方法:根据案件类型获取模板列表

        Args:
            case_type: 案件类型
            is_active: 是否只查询活跃模板

        Returns:
            DocumentTemplateDTO 列表

        Requirements: 8.6
        """
        return cast(
            list[DocumentTemplateDTO],
            self.template_query_service.get_templates_by_case_type_internal(case_type, is_active=is_active),
        )

    def list_case_templates_internal(self, is_active: bool = True) -> list[DocumentTemplateDTO]:
        return cast(
            list[DocumentTemplateDTO], self.template_query_service.list_case_templates_internal(is_active=is_active)
        )

    def get_templates_by_ids_internal(self, template_ids: list[int]) -> list[DocumentTemplateDTO]:
        return cast(list[DocumentTemplateDTO], self.template_query_service.get_templates_by_ids_internal(template_ids))
