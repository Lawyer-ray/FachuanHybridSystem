"""template/contract_template/binding_service.py 补覆盖测试。

calculate_folder_path / _find_node_path 为纯逻辑；子目录解析方法走真实 ORM
（FolderTemplate / DocumentTemplate / DocumentTemplateFolderBinding），用 django_db 标记。
"""

from __future__ import annotations

import pytest

from apps.documents.models import DocumentTemplate, DocumentTemplateFolderBinding, FolderTemplate, FolderTemplateType
from apps.documents.models.choices import DocumentTemplateType
from apps.documents.services.template.contract_template.binding_service import DocumentTemplateBindingService


def _folder_template(structure: dict | None) -> FolderTemplate:
    """不落库的文件夹模板替身（calculate_folder_path 只读 structure）。"""
    return FolderTemplate(name="案卷模板", template_type=FolderTemplateType.CASE, structure=structure)


class TestCalculateFolderPath:
    def setup_method(self):
        self.svc = DocumentTemplateBindingService()

    def test_empty_structure_returns_empty(self):
        assert self.svc.calculate_folder_path(_folder_template({}), "node_1") == ""

    def test_none_structure_returns_empty(self):
        assert self.svc.calculate_folder_path(_folder_template(None), "node_1") == ""

    def test_top_level_node_found(self):
        structure = {"children": [{"id": "node_1", "name": "1-立案材料"}]}
        assert self.svc.calculate_folder_path(_folder_template(structure), "node_1") == "1-立案材料"

    def test_nested_node_path_joined(self):
        structure = {
            "children": [
                {
                    "id": "node_1",
                    "name": "一审",
                    "children": [{"id": "node_1_2", "name": "1-起诉状", "children": []}],
                }
            ]
        }
        assert self.svc.calculate_folder_path(_folder_template(structure), "node_1_2") == "一审/1-起诉状"

    def test_unknown_node_returns_empty(self):
        structure = {"children": [{"id": "node_1", "name": "1-立案材料"}]}
        assert self.svc.calculate_folder_path(_folder_template(structure), "missing") == ""

    def test_missing_name_defaults_to_empty_string(self):
        structure = {"children": [{"id": "node_1"}]}
        assert self.svc.calculate_folder_path(_folder_template(structure), "node_1") == ""


@pytest.mark.django_db
class TestGetCaseSubdirPathInternal:
    """子目录解析。注意：绑定保存时会按文件夹结构自动计算 folder_node_path，
    因此测试数据必须给出真实 structure，而不是手写 folder_node_path。"""

    def setup_method(self):
        self.svc = DocumentTemplateBindingService()

    def _create_folder_template(self, case_types: list, structure: dict | None = None) -> FolderTemplate:
        return FolderTemplate.objects.create(
            name=f"案件文件夹{abs(hash(tuple(case_types))) % 10000}",
            template_type=FolderTemplateType.CASE,
            case_types=case_types,
            structure=structure if structure is not None else {},
        )

    def _create_binding(
        self, ft: FolderTemplate, *, node_id: str, is_active: bool = True
    ) -> DocumentTemplateFolderBinding:
        return DocumentTemplateFolderBinding.objects.create(
            document_template=DocumentTemplate.objects.create(name=f"模板-{node_id}"),
            folder_template=ft,
            folder_node_id=node_id,
            is_active=is_active,
        )

    def test_blank_inputs_return_none(self):
        assert self.svc.get_case_subdir_path_internal("", "case_documents") is None
        assert self.svc.get_case_subdir_path_internal("civil", "") is None

    def test_no_matching_folder_template_returns_none(self):
        self._create_folder_template(["criminal"])
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") is None

    def test_no_binding_returns_none(self):
        self._create_folder_template(["civil"])
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") is None

    def test_binding_by_node_id(self):
        ft = self._create_folder_template(["civil"], {"children": [{"id": "case_documents", "name": "2-案件材料"}]})
        self._create_binding(ft, node_id="case_documents")
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") == "2-案件材料"

    def test_binding_by_exact_path(self):
        # 管理员用语义键命名节点：节点 id 非语义键，但路径等于语义键
        ft = self._create_folder_template(["civil"], {"children": [{"id": "folder_x1", "name": "case_documents"}]})
        self._create_binding(ft, node_id="folder_x1")
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") == "case_documents"

    def test_binding_by_path_suffix(self):
        ft = self._create_folder_template(
            ["civil"],
            {
                "children": [
                    {"id": "parent", "name": "2-案件材料", "children": [{"id": "sub", "name": "case_documents"}]}
                ]
            },
        )
        self._create_binding(ft, node_id="sub")
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") == "2-案件材料/case_documents"

    def test_empty_case_types_folder_template_matches_any(self):
        ft = self._create_folder_template([], {"children": [{"id": "case_documents", "name": "任意目录"}]})
        self._create_binding(ft, node_id="case_documents")
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") == "任意目录"

    def test_all_wildcard_folder_template_matches(self):
        ft = self._create_folder_template(["all"], {"children": [{"id": "case_documents", "name": "通配目录"}]})
        self._create_binding(ft, node_id="case_documents")
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") == "通配目录"

    def test_binding_without_path_returns_none(self):
        # 节点不在 structure 中 → 自动计算的 folder_node_path 为空
        ft = self._create_folder_template(["civil"])
        self._create_binding(ft, node_id="case_documents")
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") is None

    def test_inactive_binding_ignored(self):
        ft = self._create_folder_template(["civil"], {"children": [{"id": "case_documents", "name": "已停用目录"}]})
        self._create_binding(ft, node_id="case_documents", is_active=False)
        assert self.svc.get_case_subdir_path_internal("civil", "case_documents") is None


@pytest.mark.django_db
class TestGetContractSubdirPathInternal:
    def setup_method(self):
        self.svc = DocumentTemplateBindingService()

    def _create_contract_folder(self, contract_types: list, structure: dict | None = None) -> FolderTemplate:
        return FolderTemplate.objects.create(
            name=f"合同文件夹{abs(hash(tuple(contract_types))) % 10000}",
            template_type=FolderTemplateType.CONTRACT,
            contract_types=contract_types,
            structure=structure if structure is not None else {},
        )

    def _create_contract_doc_template(
        self, contract_types: list, name: str = "合同模板", contract_sub_type: str = "contract"
    ) -> DocumentTemplate:
        return DocumentTemplate.objects.create(
            name=name,
            template_type=DocumentTemplateType.CONTRACT,
            contract_sub_type=contract_sub_type,
            contract_types=contract_types,
        )

    def test_blank_inputs_return_none(self):
        assert self.svc.get_contract_subdir_path_internal("", "contract") is None
        assert self.svc.get_contract_subdir_path_internal("civil", "") is None

    def test_no_matching_folder_template_returns_none(self):
        self._create_contract_folder(["criminal"])
        self._create_contract_doc_template(["civil"])
        assert self.svc.get_contract_subdir_path_internal("civil", "contract") is None

    def test_no_matching_doc_template_returns_none(self):
        self._create_contract_folder(["civil"])
        self._create_contract_doc_template(["criminal"])
        assert self.svc.get_contract_subdir_path_internal("civil", "contract") is None

    def test_binding_found_returns_path(self):
        ft = self._create_contract_folder(["civil"], {"children": [{"id": "folder_c1", "name": "1-合同文本"}]})
        dt = self._create_contract_doc_template(["civil"])
        DocumentTemplateFolderBinding.objects.create(
            document_template=dt,
            folder_template=ft,
            folder_node_id="folder_c1",
            is_active=True,
        )
        assert self.svc.get_contract_subdir_path_internal("civil", "contract") == "1-合同文本"

    def test_all_wildcard_matches(self):
        ft = self._create_contract_folder(["all"], {"children": [{"id": "folder_c2", "name": "通配目录"}]})
        dt = self._create_contract_doc_template(["all"])
        DocumentTemplateFolderBinding.objects.create(
            document_template=dt,
            folder_template=ft,
            folder_node_id="folder_c2",
            is_active=True,
        )
        assert self.svc.get_contract_subdir_path_internal("civil", "contract") == "通配目录"

    def test_no_binding_returns_none(self):
        self._create_contract_folder(["civil"])
        self._create_contract_doc_template(["civil"])
        assert self.svc.get_contract_subdir_path_internal("civil", "contract") is None
