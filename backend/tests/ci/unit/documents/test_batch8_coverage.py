"""documents 模块 batch8 覆盖测试 — 覆盖 evidence、placeholders、registry、template 等未覆盖行。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# =====================================================================
# PlaceholderRegistry — placeholders/registry.py
# =====================================================================

class TestPlaceholderRegistrySingleton:
    def setup_method(self):
        """Clear singleton state before each test."""
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        PlaceholderRegistry._instance = None
        PlaceholderRegistry._services = {}
        PlaceholderRegistry._initialized = False

    def test_singleton_returns_same_instance(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        r1 = PlaceholderRegistry()
        r2 = PlaceholderRegistry()
        assert r1 is r2

    def test_clear(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        registry = PlaceholderRegistry()
        registry._services = {"test": MagicMock}
        registry.clear()
        assert registry._services == {}


class TestPlaceholderRegistryRegistration:
    def setup_method(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        PlaceholderRegistry._instance = None
        PlaceholderRegistry._services = {}
        PlaceholderRegistry._initialized = False

    def test_register_valid_service(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class TestService(BasePlaceholderService):
            name = "test_svc"
            display_name = "Test"
            description = "Desc"
            category = "test"
            placeholder_keys = ["key1"]

            def generate(self, context_data):
                return {}

        result = PlaceholderRegistry.register(TestService)
        assert result is TestService

    def test_register_not_subclass_raises(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        class NotAService:
            name = "bad"

        with pytest.raises(ValueError, match="必须继承自 BasePlaceholderService"):
            PlaceholderRegistry.register(NotAService)

    def test_register_empty_name_raises(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class NoNameService(BasePlaceholderService):
            name = ""
            placeholder_keys = []

            def generate(self, context_data):
                return {}

        with pytest.raises(ValueError, match="必须定义 name 属性"):
            PlaceholderRegistry.register(NoNameService)

    def test_register_duplicate_raises(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class Svc1(BasePlaceholderService):
            name = "dup"
            placeholder_keys = []

            def generate(self, context_data):
                return {}

        class Svc2(BasePlaceholderService):
            name = "dup"
            placeholder_keys = []

            def generate(self, context_data):
                return {}

        PlaceholderRegistry.register(Svc1)
        from apps.core.exceptions import ConflictError
        with pytest.raises(ConflictError):
            PlaceholderRegistry.register(Svc2)


class TestPlaceholderRegistryMethods:
    def setup_method(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        PlaceholderRegistry._instance = None
        PlaceholderRegistry._services = {}
        PlaceholderRegistry._initialized = False

    def _make_service(self, name, category="cat1", keys=None):
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class Svc(BasePlaceholderService):
            pass

        Svc.name = name
        Svc.display_name = f"Display {name}"
        Svc.description = f"Desc {name}"
        Svc.category = category
        Svc.placeholder_keys = keys or [name]
        Svc.generate = lambda self, ctx: {}
        return Svc

    def test_get_service(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        Svc = self._make_service("svc_a")
        PlaceholderRegistry.register(Svc)
        registry = PlaceholderRegistry()
        instance = registry.get_service("svc_a")
        assert isinstance(instance, Svc)

    def test_get_service_not_found(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry
        from apps.core.exceptions import NotFoundError

        registry = PlaceholderRegistry()
        with pytest.raises(NotFoundError):
            registry.get_service("nonexistent")

    def test_get_services_by_category(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        Svc1 = self._make_service("svc1", category="cat_a")
        Svc2 = self._make_service("svc2", category="cat_b")
        PlaceholderRegistry.register(Svc1)
        PlaceholderRegistry.register(Svc2)
        registry = PlaceholderRegistry()
        results = registry.get_services_by_category("cat_a")
        assert len(results) == 1

    def test_get_all_services(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        Svc1 = self._make_service("all1")
        Svc2 = self._make_service("all2")
        PlaceholderRegistry.register(Svc1)
        PlaceholderRegistry.register(Svc2)
        registry = PlaceholderRegistry()
        all_svcs = registry.get_all_services()
        assert len(all_svcs) == 2

    def test_get_service_for_placeholder(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        Svc = self._make_service("for_key", keys=["my_key"])
        PlaceholderRegistry.register(Svc)
        registry = PlaceholderRegistry()
        result = registry.get_service_for_placeholder("my_key")
        assert isinstance(result, Svc)

    def test_get_service_for_placeholder_not_found(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        registry = PlaceholderRegistry()
        result = registry.get_service_for_placeholder("no_key")
        assert result is None

    def test_list_registered_services(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        Svc = self._make_service("listed", keys=["k1"])
        PlaceholderRegistry.register(Svc)
        registry = PlaceholderRegistry()
        result = registry.list_registered_services()
        assert "listed" in result
        assert result["listed"]["category"] == "cat1"

    def test_upsert_overwrites(self):
        from apps.documents.services.placeholders.registry import PlaceholderRegistry

        Svc1 = self._make_service("upsert_test")
        PlaceholderRegistry.register(Svc1)

        # upsert shouldn't raise
        from apps.documents.services.placeholders.base import BasePlaceholderService

        class Svc2(BasePlaceholderService):
            name = "upsert_test"
            placeholder_keys = ["k"]
            display_name = "Updated"
            description = "Updated desc"
            category = "new_cat"

            def generate(self, context_data):
                return {}

        registry = PlaceholderRegistry()
        registry._services["upsert_test"] = Svc2
        instance = registry.get_service("upsert_test")
        assert isinstance(instance, Svc2)


# =====================================================================
# CodePlaceholderRegistry — code_placeholders/registry.py
# =====================================================================

class TestCodePlaceholderRegistry:
    def setup_method(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry
        CodePlaceholderRegistry._instance = None

    def test_singleton(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry

        r1 = CodePlaceholderRegistry()
        r2 = CodePlaceholderRegistry()
        assert r1 is r2

    def test_register_and_list(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry, CodePlaceholderDefinition

        registry = CodePlaceholderRegistry()
        defs = [
            CodePlaceholderDefinition(key="k1", source="s1", category="c1", display_name="K1"),
            CodePlaceholderDefinition(key="k2", source="s2", category="c2", display_name="K2"),
        ]
        registry.register(defs)
        result = registry.list_definitions()
        assert len(result) == 2
        assert result[0].key == "k1"

    def test_register_skips_duplicate(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry, CodePlaceholderDefinition

        registry = CodePlaceholderRegistry()
        defs = [
            CodePlaceholderDefinition(key="dup", source="s1", category="c1"),
            CodePlaceholderDefinition(key="dup", source="s2", category="c2"),
        ]
        registry.register(defs)
        result = registry.list_definitions()
        assert len(result) == 1
        assert result[0].source == "s1"  # first wins

    def test_upsert_overwrites(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry, CodePlaceholderDefinition

        registry = CodePlaceholderRegistry()
        registry.register([CodePlaceholderDefinition(key="u1", source="s1", category="c1")])
        registry.upsert([CodePlaceholderDefinition(key="u1", source="s2", category="c2")])
        result = registry.list_definitions()
        assert len(result) == 1
        assert result[0].source == "s2"

    def test_clear(self):
        from apps.documents.services.code_placeholders.registry import CodePlaceholderRegistry, CodePlaceholderDefinition

        registry = CodePlaceholderRegistry()
        registry.register([CodePlaceholderDefinition(key="c1", source="s1", category="c1")])
        registry.clear()
        assert registry.list_definitions() == []


# =====================================================================
# expose_placeholders decorator
# =====================================================================

class TestExposePlaceholdersDecorator:
    def test_decorates_function(self):
        from apps.documents.services.code_placeholders.registry import expose_placeholders

        @expose_placeholders(keys=["key1", "key2"], source="test", category="cat")
        def my_func():
            pass

        assert hasattr(my_func, "__code_placeholder_definitions__")
        assert len(my_func.__code_placeholder_definitions__) == 2

    def test_decorates_with_metadata(self):
        from apps.documents.services.code_placeholders.registry import expose_placeholders

        @expose_placeholders(
            keys=["key1"],
            source="test",
            category="cat",
            metadata={"key1": {"display_name": "Display", "description": "Desc", "example_value": "ex"}},
        )
        def my_func():
            pass

        defs = my_func.__code_placeholder_definitions__
        assert defs[0].display_name == "Display"
        assert defs[0].description == "Desc"
        assert defs[0].example_value == "ex"

    def test_decorates_without_metadata(self):
        from apps.documents.services.code_placeholders.registry import expose_placeholders

        @expose_placeholders(keys=["k1"], source="s", category="c", description="default desc")
        def my_func():
            pass

        defs = my_func.__code_placeholder_definitions__
        assert defs[0].description == "default desc"


# =====================================================================
# EvidenceQueryService — evidence/evidence_query_service.py
# =====================================================================

class TestEvidenceQueryService:
    def test_list_evidence_items_for_digest_internal_no_ids(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()
        result = svc.list_evidence_items_for_digest_internal([], [])
        assert result == []

    def test_build_dtos_with_file_path(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()
        mock_field = MagicMock()
        mock_field.storage.path.return_value = "/media/test.pdf"
        with patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem") as mock_model:
            mock_model._meta.get_field.return_value = mock_field
            items = [{"id": 1, "order": 1, "name": "Test", "purpose": "Prove", "page_start": 1, "page_end": 5, "file": "test.pdf"}]
            result = svc._build_dtos(items)
            assert len(result) == 1
            assert result[0].file_path == "/media/test.pdf"

    def test_build_dtos_with_no_file(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService

        svc = EvidenceQueryService()
        with patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem") as mock_model:
            mock_model._meta.get_field.return_value = MagicMock()
            items = [{"id": 1, "order": 1, "name": "Test", "purpose": "Prove", "page_start": None, "page_end": None, "file": None}]
            result = svc._build_dtos(items)
            assert len(result) == 1
            assert result[0].file_path is None


# =====================================================================
# PageRangeCalculator — evidence/page_range_calculator.py
# =====================================================================

class TestPageRangeCalculator:
    def test_calculate_page_ranges(self):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator

        calculator = EvidencePageRangeCalculator()
        mock_list = MagicMock()
        mock_item1 = SimpleNamespace(page_count=3, page_start=None, page_end=None)
        mock_item2 = SimpleNamespace(page_count=2, page_start=None, page_end=None)
        mock_list.start_page = 1
        mock_list.items.filter.return_value.order_by.return_value = [mock_item1, mock_item2]

        with patch("apps.documents.services.evidence.page_range_calculator.EvidenceItem") as mock_ei:
            calculator.calculate_page_ranges(evidence_list=mock_list)
            assert mock_item1.page_start == 1
            assert mock_item1.page_end == 3
            assert mock_item2.page_start == 4
            assert mock_item2.page_end == 5
            assert mock_list.total_pages == 5

    def test_calculate_page_ranges_empty(self):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator

        calculator = EvidencePageRangeCalculator()
        mock_list = MagicMock()
        mock_list.start_page = 1
        mock_list.items.filter.return_value.order_by.return_value = []

        calculator.calculate_page_ranges(evidence_list=mock_list)
        assert mock_list.total_pages == 0


# =====================================================================
# EvidenceFileService — evidence/evidence_file_service.py
# =====================================================================

class TestEvidenceFileService:
    def test_reject_unsupported_format(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        from apps.core.exceptions import ValidationException

        svc = EvidenceFileService()
        mock_file = SimpleNamespace(name="test.exe", size=1024)
        mock_item = MagicMock()
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            svc.upload_file(item=mock_item, file=mock_file)

    def test_reject_oversized_file(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        from apps.core.exceptions import ValidationException

        svc = EvidenceFileService()
        mock_file = SimpleNamespace(name="test.pdf", size=60 * 1024 * 1024)
        mock_item = MagicMock()
        with pytest.raises(ValidationException, match="文件过大"):
            svc.upload_file(item=mock_item, file=mock_file)

    def test_delete_file_success(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        svc = EvidenceFileService()
        mock_item = MagicMock()
        mock_item.file = MagicMock()
        result = svc.delete_file(item=mock_item)
        assert result is True
        assert mock_item.file is None

    def test_delete_file_no_file(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService

        svc = EvidenceFileService()
        mock_item = MagicMock()
        mock_item.file = None
        result = svc.delete_file(item=mock_item)
        assert result is True


# =====================================================================
# EvidenceMergeUseCase — evidence/evidence_merge_usecase.py
# =====================================================================

class TestMergeProgressReporter:
    def test_report_updates_db(self):
        from apps.documents.services.evidence.evidence_merge_usecase import MergeProgressReporter

        with patch("apps.documents.services.evidence.evidence_merge_usecase.EvidenceList") as mock_el:
            reporter = MergeProgressReporter(list_id=1, min_interval_seconds=0.0)
            reporter.report(current=5, total=10, message="halfway")
            mock_el.objects.filter.assert_called_once()

    def test_report_dedup_within_interval(self):
        from apps.documents.services.evidence.evidence_merge_usecase import MergeProgressReporter

        with patch("apps.documents.services.evidence.evidence_merge_usecase.EvidenceList") as mock_el:
            reporter = MergeProgressReporter(list_id=1, min_interval_seconds=999.0)
            reporter.report(current=5, total=10, message="msg")
            mock_el.reset_mock()
            reporter.report(current=5, total=10, message="msg")
            mock_el.objects.filter.assert_not_called()


# =====================================================================
# EvidenceListPlaceholderService — evidence_list_placeholder_service.py
# =====================================================================

class TestEvidenceListPlaceholderService:
    def test_get_evidence_list_name_no_our_parties(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        mock_list = SimpleNamespace(title="Evidence List 1")
        case_data = {"case_parties": []}
        result = svc.get_evidence_list_name(mock_list, case_data)
        assert result == "Evidence List 1"

    def test_get_evidence_list_name_with_our_parties(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        mock_list = SimpleNamespace(title="Evidence List 1")
        case_data = {"case_parties": [{"is_our_client": True, "legal_status": "plaintiff", "client_name": "Client A"}]}
        result = svc.get_evidence_list_name(mock_list, case_data)
        assert result == "Evidence List 1(原告)"

    def test_get_evidence_list_name_multiple_statuses(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        mock_list = SimpleNamespace(title="List")
        case_data = {"case_parties": [
            {"is_our_client": True, "legal_status": "plaintiff"},
            {"is_our_client": True, "legal_status": "applicant"},
        ]}
        result = svc.get_evidence_list_name(mock_list, case_data)
        assert "原告" in result
        assert "申请人" in result

    def test_get_parties_brief(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        case_data = {"case_parties": [
            {"legal_status": "plaintiff", "client_name": "Client A"},
            {"legal_status": "defendant", "client_name": "Client B"},
        ]}
        result = svc.get_parties_brief(case_data)
        assert "原告" in result
        assert "被告" in result

    def test_get_parties_brief_empty(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        assert svc.get_parties_brief({"case_parties": []}) == ""

    def test_format_chinese_date_valid(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        result = svc._format_chinese_date("2026-01-15")
        assert result == "2026年01月15日"

    def test_format_chinese_date_empty(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        assert svc._format_chinese_date("") == ""

    def test_format_chinese_date_invalid(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        assert svc._format_chinese_date("not-a-date") == "not-a-date"

    def test_group_parties_by_status(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        parties = [
            {"legal_status": "plaintiff", "client_name": "A"},
            {"legal_status": "plaintiff", "client_name": "B"},
            {"legal_status": "defendant", "client_name": "C"},
        ]
        groups = svc._group_parties_by_status(parties)
        assert len(groups["plaintiff"]) == 2
        assert len(groups["defendant"]) == 1

    def test_format_ordered_groups_with_unknown_status(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        groups = {"plaintiff": ["A"], "unknown_status": ["B"]}
        lines = svc._format_ordered_groups(groups)
        assert any("原告" in line for line in lines)

    def test_get_signature_info_natural_person(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        case_data = {
            "case_parties": [{"is_our_client": True, "legal_status": "plaintiff", "client_name": "Zhang San", "client_type": "natural"}],
            "specified_date": "2026-01-15",
        }
        result = svc.get_signature_info(case_data)
        assert "原告(签名+指模)" in result
        assert "Zhang San" in result

    def test_get_signature_info_legal_person(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        case_data = {
            "case_parties": [
                {"is_our_client": True, "legal_status": "plaintiff", "client_name": "Corp A", "client_type": "legal", "legal_representative": "Li Si"}
            ],
            "specified_date": "2026-01-15",
        }
        result = svc.get_signature_info(case_data)
        assert "原告(盖章)" in result
        assert "法定代表人(签名)" in result

    def test_get_signature_info_empty_parties(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        assert svc.get_signature_info({"case_parties": []}) == ""

    def test_get_placeholder_keys(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService

        svc = EvidenceListPlaceholderService(case_service=MagicMock())
        keys = svc.get_placeholder_keys()
        assert "证据清单名称" in keys


# =====================================================================
# SupplementaryAgreementBasicService
# =====================================================================

class TestSupplementaryAgreementBasicService:
    def test_generate_with_agreement(self):
        from apps.documents.services.placeholders.supplementary.basic_service import SupplementaryAgreementBasicService

        svc = SupplementaryAgreementBasicService()
        mock_agreement = MagicMock()
        mock_agreement.name = "补充协议一"
        mock_agreement.parties.all.return_value = [SimpleNamespace(role="PRINCIPAL"), SimpleNamespace(role="PRINCIPAL"), SimpleNamespace(role="OTHER")]
        ctx = {"supplementary_agreement": mock_agreement}
        result = svc.generate(ctx)
        assert result["补充协议名称"] == "补充协议一"
        assert result["补充协议份数"] == 4  # 2 principals + 2

    def test_generate_without_agreement(self):
        from apps.documents.services.placeholders.supplementary.basic_service import SupplementaryAgreementBasicService

        svc = SupplementaryAgreementBasicService()
        result = svc.generate({})
        assert result["补充协议名称"] == ""
        assert result["补充协议份数"] == 2

    def test_generate_agreement_no_name(self):
        from apps.documents.services.placeholders.supplementary.basic_service import SupplementaryAgreementBasicService

        svc = SupplementaryAgreementBasicService()
        mock_agreement = MagicMock()
        mock_agreement.name = ""
        mock_agreement.parties.all.return_value = []
        ctx = {"supplementary_agreement": mock_agreement}
        result = svc.generate(ctx)
        assert result["补充协议名称"] == ""

    def test_calculate_copies_error(self):
        from apps.documents.services.placeholders.supplementary.basic_service import SupplementaryAgreementBasicService

        svc = SupplementaryAgreementBasicService()
        mock_agreement = MagicMock()
        mock_agreement.parties.all.side_effect = Exception("db error")
        result = svc.calculate_copies(mock_agreement)
        assert result == 2

    def test_get_current_year(self):
        from apps.documents.services.placeholders.supplementary.basic_service import SupplementaryAgreementBasicService

        svc = SupplementaryAgreementBasicService()
        year = svc.get_current_year()
        assert year.isdigit()
        assert len(year) == 4


# =====================================================================
# SupplementaryAgreementOpposingService
# =====================================================================

class TestSupplementaryAgreementOpposingService:
    def test_generate_with_agreement(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        mock_client = MagicMock()
        mock_client.name = "Opponent"
        mock_client.client_type = "natural"
        mock_client.id_number = "1234567890"
        mock_party = SimpleNamespace(role="OPPOSING", client=mock_client)
        mock_agreement = MagicMock()
        mock_agreement.parties.all.return_value = [mock_party]
        ctx = {"supplementary_agreement": mock_agreement}
        result = svc.generate(ctx)
        assert "Opponent" in result["补充协议对方当事人主体信息条款"]

    def test_generate_without_agreement(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        result = svc.generate({})
        assert result["补充协议对方当事人主体信息条款"] == ""

    def test_format_opposing_party_clause_empty(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        assert svc.format_opposing_party_clause([]) == ""

    def test_format_opposing_party_natural_person(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        mock_client = MagicMock()
        mock_client.name = "Zhang"
        mock_client.client_type = "natural"
        mock_client.id_number = "ID123"
        result = svc.format_opposing_party_clause([mock_client])
        assert "姓名" in result
        assert "签名+指模" in result

    def test_format_opposing_party_legal_person(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        mock_client = MagicMock()
        mock_client.name = "Corp"
        mock_client.client_type = "legal"
        mock_client.id_number = "USCC123"
        result = svc.format_opposing_party_clause([mock_client])
        assert "名称" in result
        assert "统一社会信用代码" in result

    def test_strip_whitespace(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        assert svc._strip_whitespace("  hello  world  ") == "helloworld"
        assert svc._strip_whitespace("") == ""
        assert svc._strip_whitespace("abc") == "abc"

    def test_strip_whitespace_special_chars(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        text = "hello​world﻿"
        assert svc._strip_whitespace(text) == "helloworld"

    def test_format_opposing_party_exception_fallback(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import SupplementaryAgreementOpposingService

        svc = SupplementaryAgreementOpposingService()
        mock_client = MagicMock()
        mock_client.name = "Fallback"
        mock_client.client_type = PropertyMock(side_effect=Exception("attr error"))
        mock_client.id_number = ""
        # The exception in the loop falls back to "名称：Fallback"
        result = svc.format_opposing_party_clause([mock_client])
        assert "Fallback" in result


# =====================================================================
# extract_placeholders — document_template/placeholder_extractor.py
# =====================================================================

class TestPlaceholderExtractor:
    def test_placeholder_pattern(self):
        from apps.documents.services.document_template.placeholder_extractor import PLACEHOLDER_PATTERN

        matches = PLACEHOLDER_PATTERN.findall("{{ name }} and {{client.id}} and {{年份}}")
        assert "name" in matches
        assert "client.id" in matches
        assert "年份" in matches

    def test_placeholder_pattern_no_match(self):
        from apps.documents.services.document_template.placeholder_extractor import PLACEHOLDER_PATTERN

        assert PLACEHOLDER_PATTERN.findall("no placeholders here") == []


# =====================================================================
# LEGAL_STATUS_DISPLAY / LEGAL_STATUS_ORDER
# =====================================================================

class TestLegalStatusConstants:
    def test_display_map_values(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import LEGAL_STATUS_DISPLAY

        assert LEGAL_STATUS_DISPLAY["plaintiff"] == "原告"
        assert LEGAL_STATUS_DISPLAY["defendant"] == "被告"
        assert LEGAL_STATUS_DISPLAY["criminal_defendant"] == "被告人"

    def test_order_list(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import LEGAL_STATUS_ORDER

        assert "plaintiff" in LEGAL_STATUS_ORDER
        assert "defendant" in LEGAL_STATUS_ORDER
        assert len(LEGAL_STATUS_ORDER) > 5
