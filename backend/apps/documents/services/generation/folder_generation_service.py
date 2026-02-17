"""
文件夹生成服务

负责根据合同类型匹配文件夹模板,生成文件夹结构,并将合同文书放置到指定位置.

Requirements: 2.1, 2.6, 2.7, 3.1, 4.1
"""

import logging
import zipfile
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Optional, cast

from apps.core.enums import CaseType
from apps.core.exceptions import NotFoundError, ValidationException

if TYPE_CHECKING:
    from apps.core.interfaces import IContractService
    from apps.documents.models import DocumentTemplate, FolderTemplate

logger = logging.getLogger(__name__)


@dataclass
class DocumentPlacement:
    """文书放置配置"""

    document_template: "DocumentTemplate"
    folder_path: str  # 相对于根目录的路径
    file_name: str  # 生成的文件名


class FolderGenerationService:
    """
    文件夹生成服务

    负责生成包含完整文件夹结构和合同文书的ZIP压缩包.

    使用 ServiceLocator 获取跨模块依赖,遵循四层架构规范.
    """

    def __init__(
        self,
        contract_service: Optional["IContractService"] = None,
        folder_binding_service: Any | None = None,
    ) -> None:
        """
        初始化服务(依赖注入)

        Args:
            contract_service: 合同服务接口(可选,延迟获取)
        """
        self._contract_service = contract_service
        self._folder_binding_service = folder_binding_service
        self._last_extract_path: str | None = None

    @property
    def contract_service(self) -> "IContractService":
        """
        延迟获取合同服务

        Returns:
            IContractService 实例
        """
        if self._contract_service is None:
            raise RuntimeError("FolderGenerationService.contract_service 未注入")
        return self._contract_service

    @property
    def folder_binding_service(self) -> Any | None:
        return self._folder_binding_service

    def find_matching_folder_template(self, case_type: str) -> Optional["FolderTemplate"]:
        """
        根据合同类型查找匹配的文件夹模板

        Args:
            case_type: 合同类型(如 'civil', 'criminal' 等)

        Returns:
            匹配的 FolderTemplate 或 None
        """
        from .pipeline import TemplateMatcher

        return cast(Optional["FolderTemplate"], TemplateMatcher().match_folder_template(case_type))

    def format_root_folder_name(self, contract: Any) -> str:
        """
        格式化根目录文件夹名称

        格式:{日期}-[{合同类型显示名}]{合同名称}
        示例:2026.01.02-[民商事]奥创公司案件

        Args:
            contract: 合同数据(Contract 实例或 ContractDataWrapper)

        Returns:
            格式化后的文件夹名称
        """
        # 获取当前日期
        today = date.today().strftime("%Y.%m.%d")

        # 获取合同类型中文显示名
        case_type = getattr(contract, "case_type", None)
        case_type_display = dict(CaseType.choices).get(case_type, case_type or "未知类型")  # type: ignore[arg-type]

        # 获取合同名称
        contract_name = getattr(contract, "name", None) or "未命名合同"

        # 组合格式化名称
        return f"{today}-[{case_type_display}]{contract_name}"

    def generate_folder_structure(self, template: "FolderTemplate", root_name: str) -> dict[str, Any]:
        """
        根据模板生成文件夹结构

        模板结构格式:
        - 标准格式:{"children": [...]} - 只有子节点,根目录名称由 root_name 提供
        - 带名称格式:{"name": "xxx", "children": [...]} - 有根目录名称

        Args:
            template: 文件夹模板
            root_name: 根目录名称(用于替换或创建根目录)

        Returns:
            文件夹结构字典,包含 name 和 children
        """
        structure = template.structure.copy() if template.structure else {}

        # 如果模板结构有根目录名称,则替换
        if structure and "name" in structure:
            structure["name"] = root_name
        else:
            # 模板结构只有 children,创建包含根目录的结构
            # 根目录名称使用 root_name
            structure = {"name": root_name, "children": structure.get("children", [])}

        return cast(dict[str, Any], structure)

    def get_document_placements(self, contract: Any, folder_template: "FolderTemplate") -> list[DocumentPlacement]:
        """
        获取文书放置配置

        Args:
            contract: 合同数据(Contract 实例或 ContractDataWrapper)
            folder_template: 文件夹模板

        Returns:
            文书放置配置列表
        """
        from apps.documents.models import (
            DocumentContractSubType,
            DocumentTemplate,
            DocumentTemplateFolderBinding,
            DocumentTemplateType,
        )

        placements: list[Any] = []

        # 查询与合同类型匹配的文书模板
        document_templates = DocumentTemplate.objects.filter(
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type=DocumentContractSubType.CONTRACT,
            is_active=True,
        )

        matched_templates: list[Any] = []
        for template in document_templates:
            contract_types = template.contract_types or []
            case_type = getattr(contract, "case_type", None)
            if case_type in contract_types or "all" in contract_types:
                matched_templates.append(template)

        # 如果没有匹配的文书模板,返回空列表(调用方会抛出异常)
        if not matched_templates:
            return []

        # 使用绑定配置确定文书放置位置
        for template in matched_templates:
            # 查询绑定配置
            binding = DocumentTemplateFolderBinding.objects.filter(
                document_template=template, folder_template=folder_template, is_active=True
            ).first()

            if binding:
                # 有绑定配置,使用指定路径
                folder_path = binding.folder_node_path or ""
            else:
                # 无绑定配置,尝试自动查找"1-合同"文件夹
                folder_path = self._find_contract_folder_path(folder_template)

            # 生成文件名
            file_name = self._generate_document_filename(contract, template)

            placements.append(
                DocumentPlacement(document_template=template, folder_path=folder_path, file_name=file_name)
            )

        return placements

    def _find_contract_folder_path(self, folder_template: "FolderTemplate") -> str:
        """
        在文件夹模板中查找"1-合同"文件夹的路径

        Args:
            folder_template: 文件夹模板

        Returns:
            合同文件夹路径,如 "顾问案件/1-律师资料/1-合同"
        """
        structure = folder_template.structure
        if not structure:
            return ""

        # 递归查找名称包含"合同"的文件夹
        path = self._find_folder_by_name(structure.get("children", []), "合同", [])
        return "/".join(path) if path else ""

    def _find_folder_by_name(self, children: list[Any], target_name: str, current_path: list[Any]) -> list[Any]:
        """
        递归查找包含指定名称的文件夹

        Args:
            children: 子文件夹列表
            target_name: 目标名称(部分匹配)
            current_path: 当前路径

        Returns:
            找到的文件夹路径列表
        """
        for child in children:
            child_name = child.get("name", "")
            child_path = current_path + [child_name]

            # 检查是否匹配(名称包含目标名称,且不包含"补充协议")
            if target_name in child_name and "补充协议" not in child_name:
                return child_path

            # 递归查找子文件夹
            result = self._find_folder_by_name(child.get("children", []), target_name, child_path)
            if result:
                return result

        return []

    def create_zip_package(self, folder_structure: dict[str, Any], documents: list[tuple[str, bytes, str]]) -> bytes:
        """
        创建ZIP打包

        Args:
            folder_structure: 文件夹结构字典
            documents: 文书列表 [(folder_path, content, filename), ...]

        Returns:
            ZIP文件内容
        """
        from .pipeline import ZipPackager

        return ZipPackager().create(folder_structure, documents)

    def generate_folder_with_documents(self, contract_id: int) -> tuple[bytes | None, str | None, str | None]:
        """
        生成包含文书的文件夹ZIP包

        Args:
            contract_id: 合同ID

        Returns:
            Tuple[ZIP内容, 文件名, 错误信息]

        Requirements: 2.6, 2.7
        """
        # 延迟导入,避免循环依赖
        from .contract_generation_service import ContractDataWrapper, ContractGenerationService

        contract_data = self.contract_service.get_contract_with_details_internal(contract_id)
        if not contract_data:
            raise NotFoundError("合同不存在")

        # 包装为类似对象的访问方式
        contract = ContractDataWrapper(contract_data)

        # 2. 查找匹配的文件夹模板
        folder_template = self.find_matching_folder_template(contract.case_type)
        if not folder_template:
            raise ValidationException(
                message="请先配置文件夹模板",
                code="NO_FOLDER_TEMPLATE",
                errors={"case_type": f"合同类型 {contract.case_type} 没有匹配的文件夹模板"},
            )

        # 3. 获取文书放置配置(检查是否有匹配的文书模板)
        document_placements = self.get_document_placements(contract, folder_template)
        if not document_placements:
            raise ValidationException(
                message="请先添加合同模板",
                code="NO_DOCUMENT_TEMPLATE",
                errors={"case_type": f"合同类型 {contract.case_type} 没有匹配的文书模板"},
            )

        # 4. 生成根目录名称
        root_name = self.format_root_folder_name(contract)

        # 5. 生成文件夹结构
        folder_structure = self.generate_folder_structure(folder_template, root_name)

        # 6. 生成文书
        contract_service = ContractGenerationService(
            contract_service=self.contract_service,
            folder_binding_service=self.folder_binding_service,
        )
        documents: list[Any] = []

        for placement in document_placements:
            try:
                # 使用模板生成合同文书
                content, _, error = contract_service.generate_contract_document(contract_id)

                if content:
                    documents.append((placement.folder_path, content, placement.file_name))
                    logger.info(
                        f"合同文书生成成功,放置路径: {placement.folder_path}/{placement.file_name}",
                        extra={
                            "contract_id": contract_id,
                            "folder_path": placement.folder_path,
                            "file_name": placement.file_name,
                        },
                    )
                elif error:
                    logger.warning(f"生成文书失败: {error}")
            except Exception as e:
                logger.warning(f"生成文书异常: {e!s}")

        # 7. 创建ZIP包
        try:
            zip_content = self.create_zip_package(folder_structure, documents)
            zip_filename = f"{root_name}.zip"

            # 8. 检查绑定并自动解压到绑定文件夹
            self._last_extract_path = self._extract_to_bound_folder_if_exists(contract_id, zip_content)

            return zip_content, zip_filename, None
        except Exception as e:
            logger.exception("创建ZIP包失败")
            raise ValidationException(f"文件夹打包失败: {e!s}") from e

    def generate_folder_with_documents_result(
        self, contract_id: int
    ) -> tuple[bytes | None, str | None, str | None, str | None]:
        zip_content, zip_filename, error = self.generate_folder_with_documents(contract_id)
        return zip_content, zip_filename, self._last_extract_path, error

    def _generate_document_filename(self, contract: Any, template: "DocumentTemplate") -> str:
        """
        生成文书文件名

        Args:
            contract: 合同数据(Contract 实例或 ContractDataWrapper)
            template: 文书模板

        Returns:
            文件名
        """
        # 使用现有的合同生成服务的文件名生成逻辑
        from .contract_generation_service import ContractGenerationService

        service = ContractGenerationService(
            contract_service=self.contract_service,
            folder_binding_service=self.folder_binding_service,
        )
        return service.generate_filename(contract, template)

    def _create_folders_in_zip(self, zip_file: zipfile.ZipFile, structure: dict[str, Any], parent_path: str) -> None:
        """
        在ZIP文件中递归创建文件夹结构

        Args:
            zip_file: ZipFile 对象
            structure: 文件夹结构
            parent_path: 父路径
        """
        if not structure:
            return

        folder_name = structure.get("name", "")
        if not folder_name:
            return

        # 构建当前文件夹路径
        current_path = f"{parent_path}/{folder_name}" if parent_path else folder_name

        # 创建文件夹(在ZIP中添加以/结尾的条目)
        zip_file.writestr(f"{current_path}/", "")

        # 递归处理子文件夹
        children = structure.get("children", [])
        for child in children:
            self._create_folders_in_zip(zip_file, child, current_path)

    def _extract_to_bound_folder_if_exists(self, contract_id: int, zip_content: bytes) -> Any:
        """
        如果合同已绑定文件夹,自动解压ZIP到绑定文件夹

        Args:
            contract_id: 合同ID
            zip_content: ZIP文件内容
        """
        if self.folder_binding_service is None:
            return None

        try:
            extract_path = self.folder_binding_service.extract_zip_to_bound_folder(
                contract_id=contract_id,
                zip_content=zip_content,
            )

            if extract_path:
                logger.info(
                    f"文件夹ZIP已自动解压到绑定文件夹: {extract_path}",
                    extra={
                        "contract_id": contract_id,
                        "extract_path": extract_path,
                        "action": "auto_extract_folder_zip",
                    },
                )
            return extract_path
        except Exception:
            logger.exception("auto_extract_folder_zip_failed", extra={"contract_id": contract_id})
            return None
