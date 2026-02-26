"""
合同生成服务

负责查找模板、构建上下文、替换关键词、生成合同文件.

Requirements: 2.1, 2.2, 3.1-3.5, 5.1-5.4
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.core.interfaces import IContractFolderBindingService, IContractService
    from apps.documents.models import DocumentTemplate

logger = logging.getLogger(__name__)


class LawyerWrapper:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data or {}

    @property
    def real_name(self) -> str:
        return str(self._data.get("lawyer_name") or self._data.get("real_name") or "")

    @property
    def username(self) -> str:
        return str(self._data.get("username") or self._data.get("lawyer_username") or "")

    @property
    def id(self) -> Any:
        return self._data.get("lawyer_id") or self._data.get("id")


class AssignmentWrapper:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data or {}
        self.lawyer = LawyerWrapper(self._data)

    @property
    def id(self) -> Any:
        return self._data.get("id")

    @property
    def is_primary(self) -> bool:
        return bool(self._data.get("is_primary", False))

    @property
    def order(self) -> Any:
        return self._data.get("order")


class AssignmentListWrapper:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = [AssignmentWrapper(x) for x in (items or [])]

    def all(self) -> list[Any]:
        return list(self._items)


class ContractDataWrapper:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data or {}
        self.assignments = AssignmentListWrapper(self._data.get("assignments") or [])

    @property
    def id(self) -> Any:
        return self._data.get("id")

    @property
    def name(self) -> str:
        return str(self._data.get("name") or "")

    @property
    def case_type(self) -> str:
        return str(self._data.get("case_type") or "")


class ContractGenerationService:
    """
    合同生成服务

    负责查找模板、构建上下文、替换关键词、生成文件.

    使用 ServiceLocator 获取跨模块依赖,遵循四层架构规范.
    """

    def __init__(
        self,
        contract_service: "IContractService" | None = None,
        folder_binding_service: "IContractFolderBindingService" | None = None,
    ) -> None:
        """
        初始化服务(依赖注入)

        Args:
            contract_service: 合同服务接口(可选,延迟获取)
        """
        self._contract_service = contract_service
        self._folder_binding_service = folder_binding_service
        self._last_saved_path: str | None = None

    @property
    def contract_service(self) -> "IContractService":
        """
        延迟获取合同服务

        Returns:
            IContractService 实例
        """
        if self._contract_service is None:
            from apps.documents.services.infrastructure.wiring import get_contract_service

            self._contract_service = get_contract_service()
        return self._contract_service

    @property
    def folder_binding_service(self) -> "IContractFolderBindingService" | None:
        return self._folder_binding_service

    def generate_contract_document(self, contract_id: int) -> tuple[bytes | None, str | None, str | None]:
        """
        生成合同文书

        Args:
            contract_id: 合同 ID

        Returns:
            Tuple[文件内容, 文件名, 错误信息]
            - 成功: (bytes, filename, None)
            - 失败: (None, None, error_message)

        Requirements: 2.1, 2.7
        """
        contract = self.contract_service.get_contract_model_internal(contract_id)
        if not contract:
            return None, None, "合同不存在"

        from .pipeline import DocxRenderer, PipelineContextBuilder

        # 2. 查找匹配模板
        template = self.find_matching_template(contract.case_type)
        if not template:
            return None, None, "请先添加合同模板"

        # 3. 检查模板文件是否存在
        file_location = template.get_file_location()
        if not file_location or not Path(file_location).exists():
            return None, None, "模板文件不存在"

        # 4. 构建上下文
        context = PipelineContextBuilder().build_contract_context(contract)

        # 5. 使用 docxtpl 渲染模板
        try:
            content = DocxRenderer().render(file_location, context)
        except Exception as e:
            logger.exception("渲染合同模板失败")
            return None, None, f"生成合同失败: {e!s}"

        # 6. 生成文件名（传入 contract_id 以便检测版本号）
        filename = self.generate_filename(contract, template, contract_id)

        # 7. 如果合同有绑定文件夹,保存到绑定文件夹
        self._last_saved_path = self._save_to_bound_folder_if_exists(
            contract_id, content, filename, "contract_documents"
        )

        return content, filename, None

    def generate_contract_document_result(
        self, contract_id: int
    ) -> tuple[bytes | None, str | None, str | None, str | None]:
        content, filename, error = self.generate_contract_document(contract_id)
        return content, filename, self._last_saved_path, error

    def find_matching_templates(self, case_type: str) -> list["DocumentTemplate"]:
        """
        查找所有匹配的文书模板(仅合同模板,不包括补充协议模板)

        Args:
            case_type: 合同类型

        Returns:
            匹配的 DocumentTemplate 列表
        """
        from apps.documents.services.template.contract_template.query_service import ContractTemplateQueryService

        return ContractTemplateQueryService().find_matching_templates(case_type)

    def find_matching_template(self, case_type: str) -> "DocumentTemplate" | None:
        """
        查找匹配的文书模板(返回第一个匹配的)

        Args:
            case_type: 合同类型

        Returns:
            匹配的 DocumentTemplate 或 None
        """
        from apps.documents.services.template.contract_template.query_service import ContractTemplateQueryService

        return ContractTemplateQueryService().find_matching_template(case_type)

    def build_context(self, contract: Any) -> dict[str, Any]:
        """
        构建替换词上下文

        Args:
            contract: Contract 实例

        Returns:
            包含所有替换词的字典
        """
        from apps.documents.services.placeholders import EnhancedContextBuilder

        context_builder = EnhancedContextBuilder()
        context_data = {"contract": contract}

        return context_builder.build_context(context_data) # type: ignore[no-any-return]

    def generate_filename(self, contract: Any, template: "DocumentTemplate", contract_id: int | None = None) -> str:
        """
        生成输出文件名

        格式:模板名称(合同name)V1_日期.docx
        例如:民商事代理合同(王小三、大小武案件)V1_20260102.docx

        如果文件已存在,自动递增版本号(V1 -> V2 -> V3)

        Args:
            contract: Contract 实例
            template: DocumentTemplate 实例
            contract_id: 合同 ID (用于检查绑定文件夹中的已有文件)

        Returns:
            格式化的文件名
        """
        from .pipeline.naming import contract_docx_filename

        template_name = template.name or "合同"
        contract_name = getattr(contract, "name", None) or "未命名合同"
        
        # 确定版本号
        version = self._get_next_version(contract_id, template_name, contract_name, "contract_documents")
        
        filename = contract_docx_filename(template_name=template_name, contract_name=contract_name, version=version)

        logger.info(
            "生成合同文件名",
            extra={"template": template_name, "contract": contract_name, "version": version, "doc_filename": filename},
        )

        return filename

    def _get_next_version(
        self, contract_id: int | None, template_name: str, contract_name: str, subdir_key: str
    ) -> str:
        """
        获取下一个可用的版本号

        检查绑定文件夹中已存在的文件,返回下一个版本号

        Args:
            contract_id: 合同 ID
            template_name: 模板名称
            contract_name: 合同名称
            subdir_key: 子目录键名

        Returns:
            版本号字符串 (如 "V1", "V2", "V3")
        """
        import re
        from datetime import date

        if not contract_id or not self.folder_binding_service:
            return "V1"

        try:
            # 获取绑定信息
            binding = self.folder_binding_service.get_binding(owner_id=contract_id)
            if not binding or not binding.folder_path:
                return "V1"

            # 构建子目录路径
            subdir_path = self.folder_binding_service._resolve_subdir_path(
                owner_type=binding.contract.case_type if hasattr(binding, "contract") else "",
                subdir_key=subdir_key,
            )
            if not subdir_path:
                return "V1"

            folder_path = Path(binding.folder_path) / subdir_path
            if not folder_path.exists():
                return "V1"

            # 构建文件名模式（不包含版本号和日期）
            template_prefix = re.sub(r"\.(docx?|doc)$", "", template_name or "合同", flags=re.IGNORECASE)
            today_str = date.today().strftime("%Y%m%d")
            # 匹配格式: 模板名称（合同名称）V数字_日期.docx
            pattern = re.compile(
                rf"^{re.escape(template_prefix)}（{re.escape(contract_name)}）V(\d+)_{today_str}\.docx$"
            )

            # 查找已存在的版本号
            max_version = 0
            for file_path in folder_path.iterdir():
                if file_path.is_file():
                    match = pattern.match(file_path.name)
                    if match:
                        version_num = int(match.group(1))
                        max_version = max(max_version, version_num)

            return f"V{max_version + 1}"

        except Exception as e:
            logger.warning("获取版本号失败,使用默认版本 V1: %s", e)
            return "V1"

    def _save_to_bound_folder_if_exists(
        self, contract_id: int, file_content: bytes, file_name: str, subdir_key: str
    ) -> str | None:
        """
        如果合同有绑定文件夹,将文件保存到绑定文件夹

        Args:
            contract_id: 合同 ID
            file_content: 文件内容
            file_name: 文件名
            subdir_key: 子目录键名
        """
        if self.folder_binding_service is None:
            return None
        try:
            saved_path = self.folder_binding_service.save_file_to_bound_folder(
                owner_id=contract_id,
                file_content=file_content,
                file_name=file_name,
                subdir_key=subdir_key,
            )
        except Exception as e:
            logger.warning(
                "保存到绑定文件夹失败: %s", e,
                extra={"contract_id": contract_id, "file_name": file_name, "error": str(e)},
            )
            return None

        if saved_path:
            logger.info(
                "文件已保存到绑定文件夹: %s", saved_path,
                extra={"contract_id": contract_id, "file_name": file_name, "saved_path": saved_path},
            )
        return saved_path
