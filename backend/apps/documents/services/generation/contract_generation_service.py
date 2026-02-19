"""
合同生成服务

负责查找模板、构建上下文、替换关键词、生成合同文件.

Requirements: 2.1, 2.2, 3.1-3.5, 5.1-5.4
"""

import logging
import os
from typing import TYPE_CHECKING, Any, Optional

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
        contract_service: Optional["IContractService"] = None,
        folder_binding_service: Optional["IContractFolderBindingService"] = None,
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
            from apps.documents.services.wiring import get_contract_service

            self._contract_service = get_contract_service()
        return self._contract_service

    @property
    def folder_binding_service(self) -> Optional["IContractFolderBindingService"]:
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
        if not file_location or not os.path.exists(file_location):
            return None, None, "模板文件不存在"

        # 4. 构建上下文
        context = PipelineContextBuilder().build_contract_context(contract)

        # 5. 使用 docxtpl 渲染模板
        try:
            content = DocxRenderer().render(file_location, context)
        except Exception as e:
            logger.exception("渲染合同模板失败")
            return None, None, f"生成合同失败: {e!s}"

        # 6. 生成文件名
        filename = self.generate_filename(contract, template)

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
        from apps.documents.services.contract_template_query_service import ContractTemplateQueryService

        return ContractTemplateQueryService().find_matching_templates(case_type)

    def find_matching_template(self, case_type: str) -> Optional["DocumentTemplate"]:
        """
        查找匹配的文书模板(返回第一个匹配的)

        Args:
            case_type: 合同类型

        Returns:
            匹配的 DocumentTemplate 或 None
        """
        from apps.documents.services.contract_template_query_service import ContractTemplateQueryService

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

        return context_builder.build_context(context_data)

    def generate_filename(self, contract: Any, template: "DocumentTemplate") -> str:
        """
        生成输出文件名

        格式:模板名称(合同name)V1_日期.docx
        例如:民商事代理合同(王小三、大小武案件)V1_20260102.docx

        Args:
            contract: Contract 实例
            template: DocumentTemplate 实例

        Returns:
            格式化的文件名
        """
        from .pipeline.naming import contract_docx_filename

        template_name = template.name or "合同"
        contract_name = getattr(contract, "name", None) or "未命名合同"
        filename = contract_docx_filename(template_name=template_name, contract_name=contract_name, version="V1")

        logger.info(
            "生成合同文件名",
            extra={"template": template_name, "contract": contract_name, "doc_filename": filename},
        )

        return filename

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
                contract_id=contract_id,
                file_content=file_content,
                file_name=file_name,
                subdir_key=subdir_key,
            )
        except Exception as e:
            logger.warning(
                f"保存到绑定文件夹失败: {e}",
                extra={"contract_id": contract_id, "file_name": file_name, "error": str(e)},
            )
            return None

        if saved_path:
            logger.info(
                f"文件已保存到绑定文件夹: {saved_path}",
                extra={"contract_id": contract_id, "file_name": file_name, "saved_path": saved_path},
            )
        return saved_path
