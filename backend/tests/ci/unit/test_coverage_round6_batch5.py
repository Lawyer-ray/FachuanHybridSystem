"""Round 6 coverage tests - batch 5: document template query, folder validation,
placeholder base/registry, enforcement services, case material query.

Covers:
- apps/documents/services/template/document_template/query_service.py
- apps/documents/services/folder_template/validation_service.py
- apps/documents/services/placeholders/base.py + registry.py
- apps/documents/services/placeholders/litigation/enforcement_party_service.py
- apps/cases/services/material/case_material_query_service.py
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# folder_template/validation_service.py
# ============================================================


class TestFolderTemplateValidation:
    def test_validate_structure_not_dict(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        ok, msg = svc.validate_structure("not_a_dict")  # type: ignore
        assert not ok
        assert "字典" in msg

    def test_valid_structure(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        ok, msg = svc.validate_structure({"children": [{"name": "folder1"}]})
        assert ok

    def test_empty_structure(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        ok, msg = svc.validate_structure({})
        assert ok

    def test_circular_reference(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        structure = {
            "children": [
                {"id": "a", "name": "A", "children": [{"id": "b", "name": "B", "children": [{"id": "a", "name": "A2"}]}]}
            ]
        }
        ok, msg = svc.validate_structure(structure)
        assert not ok
        assert "循环引用" in msg

    def test_same_id_different_branches(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        # Same ID in sibling branches is NOT a cycle
        structure = {
            "children": [
                {"id": "a", "name": "A1"},
                {"id": "a", "name": "A2"},
            ]
        }
        ok, msg = svc.validate_structure(structure)
        assert not ok
        assert "循环引用" in msg

    def test_invalid_chars_in_name(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        structure = {"children": [{"name": "bad/name"}]}
        ok, msg = svc.validate_structure(structure)
        assert not ok
        assert "无效字符" in msg

    def test_invalid_chars_colon(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        structure = {"children": [{"name": "bad:name"}]}
        ok, msg = svc.validate_structure(structure)
        assert not ok

    def test_non_list_children(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        structure = {"children": "not_a_list"}
        ok, msg = svc.validate_structure(structure)
        assert ok  # non-list children are skipped

    def test_child_not_dict(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        structure = {"children": ["not_a_dict"]}
        ok, msg = svc.validate_structure(structure)
        assert ok

    def test_no_id_no_cycle(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        structure = {"children": [{"name": "no_id"}]}
        ok, msg = svc.validate_structure(structure)
        assert ok

    def test_nested_valid(self) -> None:
        from apps.documents.services.folder_template.validation_service import FolderTemplateValidationService
        svc = FolderTemplateValidationService()
        structure = {
            "children": [
                {"name": "A", "children": [{"name": "B", "children": []}]},
            ]
        }
        ok, msg = svc.validate_structure(structure)
        assert ok


# ============================================================
# placeholders/base.py
# ============================================================


class TestBasePlaceholderService:
    def _make_service(self) -> Any:
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class ConcreteService(BasePlaceholderService):
            name = "test_service"
            display_name = "Test"
            description = "Test service"
            category = "test"
            placeholder_keys = ["key1", "key2"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {"key1": "value1"}

        return ConcreteService()

    def test_get_placeholder_keys(self) -> None:
        svc = self._make_service()
        assert svc.get_placeholder_keys() == ["key1", "key2"]

    def test_get_placeholder_keys_returns_copy(self) -> None:
        svc = self._make_service()
        keys = svc.get_placeholder_keys()
        keys.append("key3")
        assert "key3" not in svc.get_placeholder_keys()

    def test_get_placeholder_metadata_empty(self) -> None:
        svc = self._make_service()
        assert svc.get_placeholder_metadata() == {}

    def test_str(self) -> None:
        svc = self._make_service()
        assert "test_service" in str(svc)

    def test_repr(self) -> None:
        svc = self._make_service()
        assert "test_service" in repr(svc)


# ============================================================
# placeholders/registry.py
# ============================================================


class TestPlaceholderRegistry:
    def _clean_registry(self) -> None:
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        reg = PlaceholderRegistry()
        reg.clear()

    def test_singleton(self) -> None:
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        a = PlaceholderRegistry()
        b = PlaceholderRegistry()
        assert a is b

    def test_register_and_get(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        self._clean_registry()

        class TestService(BasePlaceholderService):
            name = "test_reg_svc"
            display_name = "Test"
            placeholder_keys = ["k1"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {}

        PlaceholderRegistry.register(TestService)
        reg = PlaceholderRegistry()
        svc = reg.get_service("test_reg_svc")
        assert svc.name == "test_reg_svc"
        self._clean_registry()

    def test_register_not_subclass(self) -> None:
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        self._clean_registry()
        with pytest.raises(ValueError, match="BasePlaceholderService"):
            PlaceholderRegistry.register(str)  # type: ignore
        self._clean_registry()

    def test_register_no_name(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        self._clean_registry()

        class NoNameService(BasePlaceholderService):
            name = ""

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {}

        with pytest.raises(ValueError, match="name"):
            PlaceholderRegistry.register(NoNameService)
        self._clean_registry()

    def test_get_service_not_found(self) -> None:
        from apps.core.exceptions import NotFoundError
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        reg = PlaceholderRegistry()
        with pytest.raises(NotFoundError):
            reg.get_service("nonexistent")

    def test_get_services_by_category(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        self._clean_registry()

        class CatService(BasePlaceholderService):
            name = "cat_svc"
            category = "my_cat"
            placeholder_keys = ["k"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {}

        PlaceholderRegistry.register(CatService)
        reg = PlaceholderRegistry()
        svcs = reg.get_services_by_category("my_cat")
        assert len(svcs) >= 1
        assert svcs[0].name == "cat_svc"
        self._clean_registry()

    def test_get_all_services(self) -> None:
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        reg = PlaceholderRegistry()
        all_svcs = reg.get_all_services()
        assert isinstance(all_svcs, list)

    def test_get_service_for_placeholder_found(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        self._clean_registry()

        class PkService(BasePlaceholderService):
            name = "pk_svc"
            placeholder_keys = ["my_placeholder_key"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {}

        PlaceholderRegistry.register(PkService)
        reg = PlaceholderRegistry()
        result = reg.get_service_for_placeholder("my_placeholder_key")
        assert result is not None
        assert result.name == "pk_svc"
        self._clean_registry()

    def test_get_service_for_placeholder_not_found(self) -> None:
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        reg = PlaceholderRegistry()
        result = reg.get_service_for_placeholder("totally_fake_key")
        assert result is None

    def test_list_registered_services(self) -> None:
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        reg = PlaceholderRegistry()
        result = reg.list_registered_services()
        assert isinstance(result, dict)

    def test_clear(self) -> None:
        from apps.documents.services.placeholders.base import BasePlaceholderService
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        self._clean_registry()

        class ClearTest(BasePlaceholderService):
            name = "clear_test_svc"
            placeholder_keys = ["k"]

            def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
                return {}

        PlaceholderRegistry.register(ClearTest)
        reg = PlaceholderRegistry()
        reg.clear()
        assert "clear_test_svc" not in reg._services


# ============================================================
# document_template/query_service.py
# ============================================================


class TestDocumentTemplateQueryService:
    def test_get_by_id_not_found(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            MockT.objects.filter.return_value.first.return_value = None
            svc = DocumentTemplateQueryService()
            svc._assembler = MagicMock()
            result = svc.get_template_by_id_internal(999)
            assert result is None

    def test_get_by_id_found(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            MockT.objects.filter.return_value.first.return_value = SimpleNamespace(id=1)
            svc = DocumentTemplateQueryService()
            mock_assembler = MagicMock()
            mock_assembler.to_dto.return_value = {"id": 1}
            svc._assembler = mock_assembler
            result = svc.get_template_by_id_internal(1)
            assert result == {"id": 1}

    def test_assembler_property_lazy_init(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        svc = DocumentTemplateQueryService()
        assert svc._assembler is None
        assembler = svc.assembler
        assert assembler is not None
        assert svc._assembler is assembler

    def test_get_by_function_code_unknown(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        svc = DocumentTemplateQueryService()
        svc._assembler = MagicMock()
        result = svc.get_template_by_function_code_internal("unknown_code")
        assert result is None

    def test_get_by_function_code_preservation(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            MockT.objects.filter.return_value.filter.return_value = []
            svc = DocumentTemplateQueryService()
            svc._assembler = MagicMock()
            result = svc.get_template_by_function_code_internal("preservation_application")
            assert result is None

    def test_get_by_function_code_with_templates(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            template = SimpleNamespace(id=1, case_types=None, is_active=True)
            MockT.objects.filter.return_value.filter.return_value = [template]
            svc = DocumentTemplateQueryService()
            mock_asm = MagicMock()
            mock_asm.to_dto.return_value = {"id": 1}
            svc._assembler = mock_asm
            result = svc.get_template_by_function_code_internal("preservation_application")
            assert result == {"id": 1}

    def test_get_by_function_code_with_matching_case_type(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            template = SimpleNamespace(id=1, case_types=["civil"], is_active=True)
            MockT.objects.filter.return_value.filter.return_value = [template]
            svc = DocumentTemplateQueryService()
            mock_asm = MagicMock()
            mock_asm.to_dto.return_value = {"id": 1}
            svc._assembler = mock_asm
            result = svc.get_template_by_function_code_internal(
                "preservation_application", case_type="civil"
            )
            assert result == {"id": 1}

    def test_get_by_function_code_case_type_no_match(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            template = SimpleNamespace(id=1, case_types=["criminal"], is_active=True)
            MockT.objects.filter.return_value.filter.return_value = [template]
            svc = DocumentTemplateQueryService()
            svc._assembler = MagicMock()
            result = svc.get_template_by_function_code_internal(
                "preservation_application", case_type="civil"
            )
            assert result is None

    def test_get_by_function_code_case_type_all(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            template = SimpleNamespace(id=1, case_types=["all"], is_active=True)
            MockT.objects.filter.return_value.filter.return_value = [template]
            svc = DocumentTemplateQueryService()
            mock_asm = MagicMock()
            mock_asm.to_dto.return_value = {"id": 1}
            svc._assembler = mock_asm
            result = svc.get_template_by_function_code_internal(
                "preservation_application", case_type="civil"
            )
            assert result == {"id": 1}

    def test_list_by_function_code_unknown(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        svc = DocumentTemplateQueryService()
        svc._assembler = MagicMock()
        result = svc.list_templates_by_function_code_internal("unknown_code")
        assert result == []

    def test_list_by_function_code(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            t1 = SimpleNamespace(id=1, case_types=None, is_active=True)
            MockT.objects.filter.return_value.filter.return_value = [t1]
            svc = DocumentTemplateQueryService()
            mock_asm = MagicMock()
            mock_asm.to_dto.return_value = {"id": 1}
            svc._assembler = mock_asm
            result = svc.list_templates_by_function_code_internal("preservation_application")
            assert len(result) == 1

    def test_list_by_function_code_with_case_type_filter(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            t1 = SimpleNamespace(id=1, case_types=["civil"], is_active=True)
            t2 = SimpleNamespace(id=2, case_types=["criminal"], is_active=True)
            MockT.objects.filter.return_value.filter.return_value = [t1, t2]
            svc = DocumentTemplateQueryService()
            mock_asm = MagicMock()
            mock_asm.to_dto.side_effect = lambda t: {"id": t.id}
            svc._assembler = mock_asm
            result = svc.list_templates_by_function_code_internal(
                "preservation_application", case_type="civil"
            )
            assert len(result) == 1
            assert result[0]["id"] == 1

    def test_list_case_templates(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            with patch("apps.documents.services.template.document_template.query_service.DocumentTemplateType") as MockType:
                MockType.CASE = "case"
                t1 = SimpleNamespace(id=1)
                MockT.objects.filter.return_value.filter.return_value = [t1]
                svc = DocumentTemplateQueryService()
                mock_asm = MagicMock()
                mock_asm.to_dto.return_value = {"id": 1}
                svc._assembler = mock_asm
                result = svc.list_case_templates_internal()
                assert len(result) == 1

    def test_get_templates_by_ids_empty(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        svc = DocumentTemplateQueryService()
        result = svc.get_templates_by_ids_internal([])
        assert result == []

    def test_get_templates_by_ids(self) -> None:
        from apps.documents.services.template.document_template.query_service import DocumentTemplateQueryService
        with patch("apps.documents.services.template.document_template.query_service.DocumentTemplate") as MockT:
            t1 = SimpleNamespace(id=1)
            t2 = SimpleNamespace(id=2)
            MockT.objects.filter.return_value = [t1, t2]
            svc = DocumentTemplateQueryService()
            mock_asm = MagicMock()
            mock_asm.to_dto.side_effect = lambda t: {"id": t.id}
            svc._assembler = mock_asm
            result = svc.get_templates_by_ids_internal([1, 2, 999])
            assert len(result) == 2  # 999 not found


# ============================================================
# case_material_query_service.py - additional coverage
# ============================================================


class TestCaseMaterialQueryServiceBuildGroupOrderMap:
    def test_build_group_order_map(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        rows = [
            SimpleNamespace(category="party", side="our", supervising_authority_id=None, type_id=1),
            SimpleNamespace(category="party", side="our", supervising_authority_id=None, type_id=2),
        ]
        result = svc._build_group_order_map(rows)
        assert ("party", "our", 0) in result
        assert result[("party", "our", 0)] == [1, 2]

    def test_build_group_order_map_with_supervision(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        rows = [
            SimpleNamespace(category="case", side="our", supervising_authority_id=5, type_id=10),
        ]
        result = svc._build_group_order_map(rows)
        assert ("case", "our", 5) in result

    def test_sorted_groups(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        groups = {
            1: {"type_id": 1, "type_name": "甲", "items": []},
            2: {"type_id": 2, "type_name": "乙", "items": []},
        }
        order_map = {("party", "our", 0): [2, 1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert result[0]["type_id"] == 2
        assert result[1]["type_id"] == 1

    def test_sorted_groups_unordered_tail(self) -> None:
        from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService
        svc = CaseMaterialQueryService()
        groups = {
            1: {"type_id": 1, "type_name": "乙", "items": []},
            3: {"type_id": 3, "type_name": "甲", "items": []},
        }
        order_map = {("party", "our", 0): [1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert result[0]["type_id"] == 1
        assert result[1]["type_id"] == 3  # remainder sorted by name
