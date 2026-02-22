"""Business logic services."""

from typing import Any

from apps.documents.models import DocumentTemplate, DocumentTemplateFolderBinding, FolderTemplate, DocumentTemplateType, FolderTemplateType


class DocumentTemplateBindingService:
    def calculate_folder_path(self, folder_template: FolderTemplate, folder_node_id: str) -> str:
        """
        根据节点ID计算完整的文件夹路径

        Args:
            folder_template: 文件夹模板
            folder_node_id: 节点ID

        Returns:
            文件夹路径,如 "一审/1-立案材料/1-起诉状和反诉答辩状"
        """
        structure = folder_template.structure
        if not structure:
            return ""

        path_parts: list[str] = []
        found = self._find_node_path(structure.get("children", []), folder_node_id, path_parts)
        if found:
            return "/".join(path_parts)
        return ""

    def _find_node_path(self, children: list[Any], target_id: str, path_parts: list[str]) -> bool:
        """递归查找节点并构建路径"""
        for child in children:
            if child.get("id") == target_id:
                path_parts.append(child.get("name", ""))
                return True
            # 递归查找子节点
            if self._find_node_path(child.get("children", []), target_id, path_parts):
                path_parts.insert(0, child.get("name", ""))
                return True
        return False

    def create_binding(
        self,
        document_template: DocumentTemplate,
        folder_template: FolderTemplate,
        folder_node_id: str,
        is_active: bool = True,
    ) -> DocumentTemplateFolderBinding:
        """
        创建文件模板与文件夹节点绑定

        Args:
            document_template: 文件模板
            folder_template: 文件夹模板
            folder_node_id: 节点ID
            is_active: 是否启用

        Returns:
            创建的绑定对象
        """
        # 计算文件夹路径
        folder_node_path = self.calculate_folder_path(folder_template, folder_node_id)

        return DocumentTemplateFolderBinding.objects.create(
            document_template=document_template,
            folder_template=folder_template,
            folder_node_id=folder_node_id,
            folder_node_path=folder_node_path,
            is_active=is_active,
        )

    def update_binding(
        self,
        binding: DocumentTemplateFolderBinding,
        folder_node_id: str | None = None,
        is_active: bool | None = None,
    ) -> DocumentTemplateFolderBinding:
        """
        更新绑定

        Args:
            binding: 绑定对象
            folder_node_id: 新的节点ID(可选)
            is_active: 是否启用(可选)

        Returns:
            更新后的绑定对象
        """
        if folder_node_id is not None:
            binding.folder_node_id = folder_node_id
            # 重新计算路径
            binding.folder_node_path = self.calculate_folder_path(binding.folder_template, folder_node_id)

        if is_active is not None:
            binding.is_active = is_active

        binding.save()
        return binding

    def get_case_subdir_path_internal(self, case_type: str, subdir_key: str) -> Any:
        if not case_type or not subdir_key:
            return None

        folder_templates = FolderTemplate.objects.filter(template_type=FolderTemplateType.CASE, is_active=True)
        matching_folder_template = None
        for ft in folder_templates:
            case_types = ft.case_types or []
            if not case_types or case_type in case_types or "all" in case_types:
                matching_folder_template = ft
                break
        if not matching_folder_template:
            return None

        binding = DocumentTemplateFolderBinding.objects.filter(
            folder_template=matching_folder_template,
            folder_node_id=subdir_key,
            is_active=True,
        ).first()
        if binding and binding.folder_node_path:
            return binding.folder_node_path
        return None

    def get_contract_subdir_path_internal(self, case_type: str, contract_sub_type: str) -> str | None | None:
        if not case_type or not contract_sub_type:
            return None

        folder_templates = FolderTemplate.objects.filter(template_type=FolderTemplateType.CONTRACT, is_active=True)
        matching_folder_template = None
        for ft in folder_templates:
            contract_types = ft.contract_types or []
            if case_type in contract_types or "all" in contract_types:
                matching_folder_template = ft
                break
        if not matching_folder_template:
            return None

        document_templates = DocumentTemplate.objects.filter(
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type=contract_sub_type,
            is_active=True,
        )
        matching_doc_template = None
        for dt in document_templates:
            contract_types = dt.contract_types or []
            if case_type in contract_types or "all" in contract_types:
                matching_doc_template = dt
                break
        if not matching_doc_template:
            return None

        binding = DocumentTemplateFolderBinding.objects.filter(
            document_template=matching_doc_template,
            folder_template=matching_folder_template,
            is_active=True,
        ).first()
        if binding is not None:
            return binding.folder_node_path  # type: ignore
        return None
