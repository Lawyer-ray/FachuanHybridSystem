"""
文件夹生成服务

负责根据合同类型匹配文件夹模板,生成文件夹结构,并将合同文书放置到指定位置.

Requirements: 2.1, 2.6, 2.7, 3.1, 4.1
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from django.utils.translation import gettext_lazy as _

from apps.core.models.enums import CaseType
from apps.core.exceptions import NotFoundError, ValidationException

if TYPE_CHECKING:
    from apps.core.interfaces import IContractService
    from apps.documents.models import DocumentTemplate, FolderTemplate

logger = logging.getLogger(__name__)


@dataclass
class DocumentPlacement:
    """文书放置配置"""

    document_template: DocumentTemplate
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
        contract_service: IContractService | None = None,
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
    def contract_service(self) -> IContractService:
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

    def find_matching_folder_template(self, case_type: str) -> FolderTemplate | None:
        """
        根据合同类型查找匹配的文件夹模板

        Args:
            case_type: 合同类型(如 'civil', 'criminal' 等)

        Returns:
            匹配的 FolderTemplate 或 None
        """
        from .pipeline import TemplateMatcher

        return cast("FolderTemplate | None", TemplateMatcher().match_folder_template(case_type))

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
        case_type_display = dict(CaseType.choices).get(case_type, case_type or "未知类型")  # type: ignore[no-any-return]
        # 获取合同名称
        contract_name = getattr(contract, "name", None) or "未命名合同"

        # 组合格式化名称
        return f"{today}-[{case_type_display}]{contract_name}"

    def generate_folder_structure(self, template: FolderTemplate, root_name: str) -> dict[str, Any]:
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

        # 如果模板结构有根目录名称，则替换
        if structure and "name" in structure:
            structure["name"] = root_name
        else:
            # 模板结构只有 children，创建包含根目录的结构
            children = structure.get("children", [])
            structure = {"name": root_name, "children": children}

        return cast(dict[str, Any], structure)

    def get_document_placements(self, contract: Any, folder_template: FolderTemplate) -> list[DocumentPlacement]:
        """
        获取文书放置配置

        查询所有绑定到该文件夹模板的文件模板，并根据合同类型进行匹配

        Args:
            contract: 合同数据(Contract 实例或 ContractDataWrapper)
            folder_template: 文件夹模板

        Returns:
            文书放置配置列表
        """
        from apps.documents.models import DocumentTemplateFolderBinding

        placements: list[Any] = []
        case_type = getattr(contract, "case_type", None)

        # 查询所有绑定到该文件夹模板的文件模板
        bindings = DocumentTemplateFolderBinding.objects.filter(
            folder_template=folder_template, is_active=True
        ).select_related("document_template")

        for binding in bindings:
            template = binding.document_template

            # 检查模板是否启用
            if not template.is_active:
                continue

            # 检查模板是否匹配合同类型
            contract_types = template.contract_types or []
            if case_type not in contract_types and "all" not in contract_types:
                continue

            # 使用绑定配置的路径
            folder_path = binding.folder_node_path or ""

            logger.info(
                "找到绑定配置: 模板=%s, 节点ID=%s, 路径=%s",
                template.name,
                binding.folder_node_id,
                folder_path,
                extra={
                    "template_name": template.name,
                    "folder_node_id": binding.folder_node_id,
                    "folder_path": folder_path,
                },
            )

            # 生成文件名
            file_name = self._generate_document_filename(contract, template)

            placements.append(
                DocumentPlacement(document_template=template, folder_path=folder_path, file_name=file_name)
            )

        return placements

    def _find_contract_folder_path(self, folder_template: FolderTemplate) -> str:
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
                message=_("请先配置文件夹模板"),
                code="NO_FOLDER_TEMPLATE",
                errors={"case_type": f"合同类型 {contract.case_type} 没有匹配的文件夹模板"},
            )

        # 3. 获取文书放置配置(检查是否有匹配的文书模板)
        document_placements = self.get_document_placements(contract, folder_template)

        # 4. 生成根目录名称
        root_name = self.format_root_folder_name(contract)

        # 5. 生成文件夹结构
        folder_structure = self.generate_folder_structure(folder_template, root_name)

        # 6. 生成文书
        from .pipeline import DocxRenderer, PipelineContextBuilder

        documents: list[Any] = []

        # 获取合同数据用于构建上下文
        contract_model = self.contract_service.get_contract_model_internal(contract_id)
        if not contract_model:
            raise NotFoundError("合同不存在")

        for placement in document_placements:
            try:
                # 检查模板文件是否存在
                file_location = placement.document_template.get_file_location()
                if not file_location or not Path(file_location).exists():
                    logger.warning(
                        "模板文件不存在: %s",
                        placement.document_template.name,
                        extra={"template_name": placement.document_template.name},
                    )
                    continue

                # 构建上下文
                context = PipelineContextBuilder().build_contract_context(contract_model)

                # 渲染模板
                content = DocxRenderer().render(file_location, context)

                if content:
                    documents.append((placement.folder_path, content, placement.file_name))
                    logger.info(
                        "文书生成成功: %s, 放置路径: %s/%s",
                        placement.document_template.name,
                        placement.folder_path,
                        placement.file_name,
                        extra={
                            "contract_id": contract_id,
                            "template_name": placement.document_template.name,
                            "folder_path": placement.folder_path,
                            "file_name": placement.file_name,
                        },
                    )
            except Exception as e:
                logger.warning(
                    "生成文书异常: %s - %s",
                    placement.document_template.name,
                    e,
                    extra={"template_name": placement.document_template.name, "error": str(e)},
                )

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

    def generate_case_folder_with_documents(
        self,
        case: Any,
        folder_template: FolderTemplate,
        root_name: str,
        *,
        wrap_folder_name: str | None = None,
    ) -> bytes:
        """
        生成案件文件夹（包含绑定文档和特殊文件夹内容）。

        特殊文件夹处理：
        - "身份证明"文件夹：放入本案所有当事人的证件材料（ClientIdentityDoc）
        - "委托材料"文件夹：放入本案指派律师的执业证文件（Lawyer.license_pdf）
        - "执行依据及生效证明"文件夹：放入本案已生效的案号裁判文书（CaseNumber.document_file）

        Args:
            case: Case 实例
            folder_template: 文件夹模板
            root_name: 根目录名称
            wrap_folder_name: 若提供，则将所有内容包裹在此文件夹下（合同有多个案件时使用）

        Returns:
            ZIP 文件内容（bytes）
        """
        from pathlib import Path

        from apps.documents.models import DocumentTemplateFolderBinding
        from apps.documents.services.generation.pipeline import DocxRenderer
        from apps.documents.services.placeholders import EnhancedContextBuilder

        # 1. 生成文件夹结构
        folder_structure = self.generate_folder_structure(folder_template, root_name)
        # raw_structure 是不经单子节点优化的结构，根为 root_name（案件文件夹的根）
        raw_structure = {"name": root_name, "children": folder_structure.get("children", [])}
        # 案件文件夹用 raw_structure 作为 ZIP 结构（不以"执行"等单子节点为根）
        folder_structure = raw_structure

        # 2. 查询绑定到该文件夹模板的文档模板
        bindings = DocumentTemplateFolderBinding.objects.filter(
            folder_template=folder_template,
            is_active=True,
        ).select_related("document_template")

        # 3. 构建案件上下文并渲染文档
        documents: list[tuple[str, bytes, str]] = []
        context = EnhancedContextBuilder().build_context({"case": case, "case_id": case.id})  # type: ignore[typeddict-unknown-key]
        # raw_structure 的根才是案件文件夹真正的根（root_name），用于路径剥离
        root_folder_name = raw_structure.get("name", "")

        for binding in bindings:
            template = binding.document_template
            if not template.is_active:
                continue

            file_location = template.get_file_location()
            if not file_location or not Path(file_location).exists():
                logger.warning(
                    "案件模板文件不存在: %s",
                    template.name,
                    extra={"template_name": template.name},
                )
                continue

            folder_path = binding.folder_node_path or ""
            if folder_path.startswith(f"{root_folder_name}/"):
                folder_path = folder_path[len(f"{root_folder_name}/") :]

            # 法定代表人身份证明书：每个我方法人各生成一份
            if "法定代表人身份证明书" in template.name:
                from apps.client.models import Client
                from apps.documents.services.generation.authorization_material_generation_service import (
                    AuthorizationMaterialGenerationService,
                )

                our_legal_entities = list(
                    case.parties.select_related("client").filter(
                        client__is_our_client=True, client__client_type=Client.LEGAL
                    ).select_related("client")
                )
                if not our_legal_entities:
                    logger.info(
                        "案件文件夹 - 跳过法定代表人身份证明书（我方无法人）",
                        extra={"case_id": case.id, "template_name": template.name},
                    )
                    continue

                for party in our_legal_entities:
                    try:
                        # 使用与单独点击"法定代表人身份证明书"相同的上下文构建逻辑
                        auth_service = AuthorizationMaterialGenerationService()
                        client_context = auth_service._build_context(case=case, client=party.client)
                        content = DocxRenderer().render(file_location, client_context)
                        # 使用与单独点击"法定代表人身份证明书"相同的文件名生成逻辑
                        # 日期使用今日日期
                        from django.utils import timezone
                        date_str = timezone.now().strftime("%Y%m%d")
                        filename = f"法定代表人身份证明书({party.client.name})V1_{date_str}.docx"
                        documents.append((folder_path, content, filename))
                        logger.info(
                            "案件文件夹 - 法定代表人身份证明书已生成: %s → %s",
                            party.client.name,
                            folder_path,
                            extra={"case_id": case.id, "client": party.client.name},
                        )
                    except Exception as e:
                        logger.warning(
                            "案件文件夹 - 法定代表人身份证明书渲染异常: %s - %s",
                            party.client.name,
                            e,
                            extra={"client": party.client.name, "error": str(e)},
                        )
                continue

            # 授权委托书：使用 AuthorizationMaterialGenerationService 的 _build_power_of_attorney_context
            # 构建上下文（包含 selected_clients），然后用绑定的模板文件渲染
            if "授权委托书" in template.name:
                from apps.documents.services.generation.authorization_material_generation_service import (
                    AuthorizationMaterialGenerationService,
                )
                from apps.documents.services.generation.pipeline import DocxRenderer

                our_parties = [
                    p for p in case.parties.select_related("client").all()
                    if getattr(getattr(p, "client", None), "is_our_client", False)
                ]
                if not our_parties:
                    logger.info(
                        "案件文件夹 - 跳过授权委托书（无我方当事人）",
                        extra={"case_id": case.id, "template_name": template.name},
                    )
                    continue

                try:
                    auth_service = AuthorizationMaterialGenerationService()
                    # _build_power_of_attorney_context 在调用 EnhancedContextBuilder 之前就把
                    # selected_clients 放入 context_data，保证 PowerOfAttorneyPlaceholderService 能读到
                    ctx = auth_service._build_power_of_attorney_context(  # type: ignore[attr-defined]
                        case=case,
                        selected_clients=[p.client for p in our_parties],
                    )
                    content = DocxRenderer().render(file_location, ctx)
                    # 使用与单独点击"授权委托书"相同的文件名生成逻辑
                    filename = auth_service._build_power_of_attorney_filename(  # type: ignore[attr-defined]
                        case=case,
                        selected_clients=[p.client for p in our_parties],
                    )
                    documents.append((folder_path, content, filename))
                    logger.info(
                        "案件文件夹 - 授权委托书已生成: %s",
                        folder_path,
                        extra={"case_id": case.id, "template_name": template.name, "client_count": len(our_parties)},
                    )
                except Exception as e:
                    logger.warning(
                        "案件文件夹 - 授权委托书渲染异常: %s - %s",
                        template.name,
                        e,
                        extra={"template_name": template.name, "error": str(e)},
                    )
                continue

            # 所函：使用 AuthorizationMaterialGenerationService 的文件名生成逻辑
            if "所函" in template.name:
                from apps.documents.services.generation.authorization_material_generation_service import (
                    AuthorizationMaterialGenerationService,
                )

                try:
                    auth_service = AuthorizationMaterialGenerationService()
                    # 先渲染模板（使用与单独点击"所函"相同的上下文构建逻辑）
                    ctx = auth_service._build_context(case=case)
                    content = DocxRenderer().render(file_location, ctx)
                    # 使用与单独点击"所函"相同的文件名生成逻辑
                    filename = auth_service._build_authority_letter_filename(  # type: ignore[attr-defined]
                        case_name=case.name or "案件",
                    )
                    documents.append((folder_path, content, filename))
                    logger.info(
                        "案件文件夹 - 所函已生成: %s",
                        folder_path,
                        extra={"case_id": case.id, "template_name": template.name},
                    )
                    continue
                except Exception as e:
                    logger.warning(
                        "案件文件夹 - 所函渲染异常: %s - %s",
                        template.name,
                        e,
                        extra={"template_name": template.name, "error": str(e)},
                    )
                    continue

            try:
                content = DocxRenderer().render(file_location, context)
                # 生成文件名：模板名称(案件名称)V1_日期.docx
                # 日期优先使用 specified_date，否则使用今日日期
                from django.utils import timezone
                if case.specified_date:
                    date_str = case.specified_date.strftime("%Y%m%d")
                else:
                    date_str = timezone.now().strftime("%Y%m%d")
                case_name = case.name or "案件"
                filename = f"{template.name}({case_name})V1_{date_str}.docx"
                documents.append((folder_path, content, filename))
                logger.info(
                    "案件文件夹 - 文书生成成功: %s → %s",
                    template.name,
                    folder_path,
                    extra={"case_id": case.id, "template_name": template.name, "folder_path": folder_path},
                )
            except Exception as e:
                logger.warning(
                    "案件文件夹 - 文书渲染异常: %s - %s",
                    template.name,
                    e,
                    extra={"template_name": template.name, "error": str(e)},
                )

        # 4. 查找特殊文件夹路径（基于原始结构，返回相对于根的路径）
        special_paths = self._find_special_folder_paths(raw_structure)

        identity_paths: list[str] = special_paths.get("身份证明", [])
        attorney_paths: list[str] = special_paths.get("委托材料", [])
        execution_paths: list[str] = special_paths.get("执行依据及生效证明", [])

        # 去掉特殊文件夹路径中与 ZIP 根目录重复的前缀
        def strip_root_prefix(paths: list[str], root: str) -> list[str]:
            prefix = f"{root}/"
            return [p[len(prefix):] if p.startswith(prefix) else p for p in paths]

        identity_paths = strip_root_prefix(identity_paths, root_folder_name)
        attorney_paths = strip_root_prefix(attorney_paths, root_folder_name)
        execution_paths = strip_root_prefix(execution_paths, root_folder_name)

        # 5. 放入当事人证件材料 → "身份证明"文件夹
        from apps.core.services.storage_service import to_media_abs

        for identity_path in identity_paths:
            for party in case.parties.select_related("client"):
                for identity_doc in party.client.identity_docs.all():
                    if not identity_doc.file_path:
                        continue
                    try:
                        abs_path = to_media_abs(identity_doc.file_path)
                        if abs_path.exists():
                            content = abs_path.read_bytes()
                            suffix = abs_path.suffix
                            # 证件类型显示名称：去掉 "/" 避免路径问题，统一改为 "法定代表人身份证"
                            doc_type_display = identity_doc.get_doc_type_display().replace("/", "身份证").replace("负责人身份证", "法定代表人身份证")
                            filename = f"{party.client.name}_{doc_type_display}{suffix}"
                            documents.append((identity_path, content, filename))
                            logger.info(
                                "案件文件夹 - 证件材料已添加: %s → %s",
                                filename,
                                identity_path,
                            )
                    except Exception as e:
                        logger.warning("读取证件文件失败: %s - %s", identity_doc.file_path, e)

        # 6. 放入律师执业证 → "委托材料"文件夹
        for attorney_path in attorney_paths:
            for assignment in case.assignments.select_related("lawyer"):
                lawyer = assignment.lawyer
                if not lawyer.license_pdf:
                    continue
                try:
                    # license_pdf 是 FileField，.path 就是完整的文件系统路径
                    abs_path = Path(lawyer.license_pdf.path)
                    if abs_path.exists():
                        content = abs_path.read_bytes()
                        filename = f"{lawyer.real_name or lawyer.username}_执业证.pdf"
                        documents.append((attorney_path, content, filename))
                        logger.info(
                            "案件文件夹 - 律师执业证已添加: %s → %s",
                            filename,
                            attorney_path,
                        )
                except Exception as e:
                    logger.warning("读取律师执业证失败: %s - %s", lawyer.username, e)

        # 7. 放入已生效案号裁判文书 → "执行依据及生效证明"文件夹
        for exec_path in execution_paths:
            for case_number in case.case_numbers.filter(is_active=True).exclude(document_file=""):
                if not case_number.document_file:
                    continue
                try:
                    # document_file 是 FileField，使用 .path 获取实际文件路径
                    abs_path = Path(case_number.document_file.path)
                    if abs_path.exists():
                        content = abs_path.read_bytes()
                        filename = abs_path.name
                        if not filename.lower().endswith(".pdf"):
                            filename = f"{filename}.pdf"
                        documents.append((exec_path, content, filename))
                        logger.info(
                            "案件文件夹 - 执行依据已添加: %s → %s",
                            filename,
                            exec_path,
                        )
                except Exception as e:
                    logger.warning("读取案号裁判文书失败: %s - %s", case_number.number, e)

        # 8. 若有包裹文件夹，需要将所有文档路径加上包裹前缀
        if wrap_folder_name:
            wrapped_documents: list[tuple[str, bytes, str]] = []
            for doc_folder_path, content, filename in documents:
                new_path = f"{wrap_folder_name}/{doc_folder_path}" if doc_folder_path else wrap_folder_name
                wrapped_documents.append((new_path, content, filename))
            documents = wrapped_documents

        # 9. 创建 ZIP 包
        return self.create_zip_package(folder_structure, documents)

    def _find_special_folder_paths(
        self, structure: dict[str, Any], parent_path: str = ""
    ) -> dict[str, list[str]]:
        """
        递归查找特殊文件夹路径。

        Args:
            structure: 文件夹结构
            parent_path: 父路径

        Returns:
            { "身份证明": [路径1, 路径2], "委托材料": [...], ... }
        """
        result: dict[str, list[str]] = {
            "身份证明": [],
            "委托材料": [],
            "执行依据及生效证明": [],
        }
        if not structure:
            return result

        folder_name = structure.get("name", "")
        current_path = f"{parent_path}/{folder_name}" if parent_path else folder_name

        children = structure.get("children", [])

        # 检查是否匹配特殊文件夹名称（部分匹配）
        for keyword in result:
            if keyword in folder_name:
                result[keyword].append(current_path)

        # 递归处理子文件夹
        for child in children:
            child_result = self._find_special_folder_paths(child, current_path)
            for key, paths in child_result.items():
                result[key].extend(paths)

        return result

    def _generate_document_filename(self, contract: Any, template: DocumentTemplate) -> str:
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
                    "文件夹ZIP已自动解压到绑定文件夹: %s",
                    extract_path,
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
