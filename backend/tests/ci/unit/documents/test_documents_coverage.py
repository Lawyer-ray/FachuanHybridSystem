"""Coverage tests for apps/documents 0% files.

Covers:
- apps/documents/presenters/template_names_presenter.py
- apps/documents/services/generation/pipeline/naming.py
- apps/documents/services/generation/outputs.py
- apps/documents/services/document_service_adapter.py
- apps/documents/services/evidence/evidence_merge_usecase.py
- apps/documents/services/generation/generation_task_service.py
- apps/documents/services/case_contract_query.py
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException


# ── template_names_presenter ────────────────────────────────────────────────


class TestFormatTemplateNames:
    """apps/documents/presenters/template_names_presenter.py"""

    def test_empty_list_returns_no_match(self) -> None:
        from apps.documents.presenters.template_names_presenter import format_template_names

        assert format_template_names([]) == "无匹配模板"

    def test_single_name(self) -> None:
        from apps.documents.presenters.template_names_presenter import format_template_names

        assert format_template_names(["起诉状"]) == "起诉状"

    def test_multiple_names_joined(self) -> None:
        from apps.documents.presenters.template_names_presenter import format_template_names

        result = format_template_names(["起诉状", "答辩状", "证据目录"])
        assert result == "起诉状、答辩状、证据目录"

    def test_filters_empty_strings(self) -> None:
        from apps.documents.presenters.template_names_presenter import format_template_names

        result = format_template_names(["起诉状", "", "答辩状", None])
        assert result == "起诉状、答辩状"

    def test_all_empty_returns_no_match(self) -> None:
        from apps.documents.presenters.template_names_presenter import format_template_names

        assert format_template_names(["", None, ""]) == "无匹配模板"

    def test_generator_input(self) -> None:
        from apps.documents.presenters.template_names_presenter import format_template_names

        gen = (name for name in ["a", "b"])
        assert format_template_names(gen) == "a、b"


# ── generation/pipeline/naming.py ──────────────────────────────────────────


class TestNormalizeVersion:
    """_normalize_version() 纯函数测试。"""

    def test_v1_becomes_1(self) -> None:
        from apps.documents.services.generation.pipeline.naming import _normalize_version

        assert _normalize_version("V1") == "1"

    def test_v10_becomes_10(self) -> None:
        from apps.documents.services.generation.pipeline.naming import _normalize_version

        assert _normalize_version("V10") == "10"

    def test_lowercase_v_stripped(self) -> None:
        from apps.documents.services.generation.pipeline.naming import _normalize_version

        assert _normalize_version("v2") == "2"

    def test_no_v_prefix(self) -> None:
        from apps.documents.services.generation.pipeline.naming import _normalize_version

        assert _normalize_version("3") == "3"

    def test_v1_dot_0_becomes_1_dot_0(self) -> None:
        from apps.documents.services.generation.pipeline.naming import _normalize_version

        assert _normalize_version("V1.0") == "1.0"


class TestContractDocxFilename:
    """contract_docx_filename() 测试。"""

    @patch("apps.documents.services.generation.pipeline.naming.FilenameTemplateService")
    @patch("apps.documents.services.generation.pipeline.naming._today_compact", return_value="20260101")
    def test_basic_filename(self, mock_date, mock_svc) -> None:
        from apps.documents.services.generation.pipeline.naming import contract_docx_filename

        mock_svc.render_generated_doc.return_value = "委托代理合同（甲乙公司）V1_20260101"
        result = contract_docx_filename(template_name="委托代理合同", contract_name="甲乙公司", version="V1")
        assert result.endswith(".docx")
        mock_svc.render_generated_doc.assert_called_once()

    @patch("apps.documents.services.generation.pipeline.naming.FilenameTemplateService")
    @patch("apps.documents.services.generation.pipeline.naming._today_compact", return_value="20260101")
    def test_template_name_strips_docx_ext(self, mock_date, mock_svc) -> None:
        from apps.documents.services.generation.pipeline.naming import contract_docx_filename

        mock_svc.render_generated_doc.return_value = "result"
        contract_docx_filename(template_name="合同.docx", contract_name="test")
        call_kwargs = mock_svc.render_generated_doc.call_args[1]
        assert call_kwargs["doc_type"] == "合同"

    @patch("apps.documents.services.generation.pipeline.naming.FilenameTemplateService")
    @patch("apps.documents.services.generation.pipeline.naming._today_compact", return_value="20260101")
    def test_empty_template_name_defaults(self, mock_date, mock_svc) -> None:
        from apps.documents.services.generation.pipeline.naming import contract_docx_filename

        mock_svc.render_generated_doc.return_value = "result"
        contract_docx_filename(template_name="", contract_name="")
        call_kwargs = mock_svc.render_generated_doc.call_args[1]
        assert call_kwargs["doc_type"] == "合同"
        assert call_kwargs["case_name"] == "未命名合同"


class TestSupplementaryAgreementDocxFilename:
    """supplementary_agreement_docx_filename() 测试。"""

    @patch("apps.documents.services.generation.pipeline.naming.FilenameTemplateService")
    @patch("apps.documents.services.generation.pipeline.naming._today_compact", return_value="20260101")
    def test_basic_filename(self, mock_date, mock_svc) -> None:
        from apps.documents.services.generation.pipeline.naming import supplementary_agreement_docx_filename

        mock_svc.render_generated_doc.return_value = "补充协议（甲乙公司）V1_20260101"
        result = supplementary_agreement_docx_filename(agreement_name="补充协议", contract_name="甲乙公司")
        assert result.endswith(".docx")

    @patch("apps.documents.services.generation.pipeline.naming.FilenameTemplateService")
    @patch("apps.documents.services.generation.pipeline.naming._today_compact", return_value="20260101")
    def test_empty_names_defaults(self, mock_date, mock_svc) -> None:
        from apps.documents.services.generation.pipeline.naming import supplementary_agreement_docx_filename

        mock_svc.render_generated_doc.return_value = "result"
        supplementary_agreement_docx_filename(agreement_name="", contract_name="")
        call_kwargs = mock_svc.render_generated_doc.call_args[1]
        assert call_kwargs["doc_type"] == "补充协议"
        assert call_kwargs["case_name"] == "未命名合同"


# ── generation/outputs.py (Pydantic models) ────────────────────────────────


class TestPydanticOutputs:
    """generation/outputs.py Pydantic 模型验证。"""

    def test_party_info_creation(self) -> None:
        from apps.documents.services.generation.outputs import PartyInfo

        p = PartyInfo(name="张三", role="原告", id_number="123", address="北京市")
        assert p.name == "张三"
        assert p.role == "原告"

    def test_party_info_defaults(self) -> None:
        from apps.documents.services.generation.outputs import PartyInfo

        p = PartyInfo(name="张三", role="原告")
        assert p.id_number == ""
        assert p.address == ""

    def test_complaint_output_creation(self) -> None:
        from apps.documents.services.generation.outputs import ComplaintOutput, PartyInfo

        c = ComplaintOutput(
            title="民事起诉状",
            parties=[PartyInfo(name="张三", role="原告")],
            litigation_request="请求判令",
            facts_and_reasons="事实理由",
        )
        assert c.title == "民事起诉状"
        assert len(c.parties) == 1
        assert c.evidence == []

    def test_defense_output_creation(self) -> None:
        from apps.documents.services.generation.outputs import DefenseOutput, PartyInfo

        d = DefenseOutput(
            title="答辩状",
            parties=[PartyInfo(name="李四", role="被告")],
            defense_opinion="不同意",
            defense_reasons="理由",
        )
        assert d.title == "答辩状"
        assert d.evidence == []

    def test_execution_request_output_defaults(self) -> None:
        from apps.documents.services.generation.outputs import ExecutionRequestOutput

        e = ExecutionRequestOutput()
        assert e.principal is None
        assert e.confirmed_interest == 0
        assert e.rate_type == "lpr"

    def test_complaint_output_with_evidence(self) -> None:
        from apps.documents.services.generation.outputs import ComplaintOutput, PartyInfo

        c = ComplaintOutput(
            title="起诉状",
            parties=[],
            litigation_request="req",
            facts_and_reasons="facts",
            evidence=["证据1", "证据2"],
        )
        assert c.evidence == ["证据1", "证据2"]


# ── document_service_adapter.py ────────────────────────────────────────────


class TestDocumentServiceAdapter:
    """DocumentServiceAdapter 方法测试 (mock 依赖)。"""

    def _make_adapter(self) -> tuple:
        from apps.documents.services.document_service_adapter import DocumentServiceAdapter

        tq = MagicMock()
        tm = MagicMock()
        tb = MagicMock()
        adapter = DocumentServiceAdapter(
            template_query_service=tq,
            template_matching_service=tm,
            template_binding_service=tb,
        )
        return adapter, tq, tm, tb

    def test_lazy_init_template_query_service(self) -> None:
        from apps.documents.services.document_service_adapter import DocumentServiceAdapter

        adapter = DocumentServiceAdapter()
        with patch(
            "apps.documents.services.document_service_adapter.DocumentServiceAdapter.template_query_service",
            new_callable=lambda: property(lambda self: "mocked"),
        ):
            pass
        # 未注入时访问属性会触发 lazy import
        assert adapter._template_query_service is None

    def test_get_matched_document_templates_success(self) -> None:
        adapter, _, tm, _ = self._make_adapter()
        tm.find_matching_case_document_template_names.return_value = ["起诉状", "答辩状"]
        result = adapter.get_matched_document_templates("civil")
        assert result == "起诉状、答辩状"

    def test_get_matched_document_templates_exception(self) -> None:
        adapter, _, tm, _ = self._make_adapter()
        tm.find_matching_case_document_template_names.side_effect = RuntimeError("db error")
        result = adapter.get_matched_document_templates("civil")
        assert result == "查询失败"

    def test_get_matched_folder_templates_with_legal_status_success(self) -> None:
        adapter, _, tm, _ = self._make_adapter()
        tm.find_matching_case_folder_template_names_with_legal_status.return_value = ["模板A"]
        result = adapter.get_matched_folder_templates_with_legal_status("civil", ["plaintiff"])
        assert result == "模板A"

    def test_get_matched_folder_templates_with_legal_status_exception(self) -> None:
        adapter, _, tm, _ = self._make_adapter()
        tm.find_matching_case_folder_template_names_with_legal_status.side_effect = RuntimeError("err")
        result = adapter.get_matched_folder_templates_with_legal_status("civil", ["plaintiff"])
        assert result == "查询失败"

    def test_get_folder_binding_path_delegates(self) -> None:
        adapter, _, _, tb = self._make_adapter()
        tb.get_case_subdir_path_internal.return_value = "1-律师资料/2-案件文书"
        result = adapter.get_folder_binding_path("civil", "case_documents")
        assert result == "1-律师资料/2-案件文书"

    def test_get_folder_binding_path_raises_on_error(self) -> None:
        adapter, _, _, tb = self._make_adapter()
        tb.get_case_subdir_path_internal.side_effect = RuntimeError("err")
        with pytest.raises(RuntimeError):
            adapter.get_folder_binding_path("civil", "case_documents")

    def test_get_template_by_id_internal(self) -> None:
        adapter, tq, _, _ = self._make_adapter()
        tq.get_template_by_id_internal.return_value = "dto"
        assert adapter.get_template_by_id_internal(1) == "dto"

    def test_check_has_matching_templates(self) -> None:
        adapter, _, tm, _ = self._make_adapter()
        tm.check_has_matching_templates.return_value = {"has_folder": True, "has_document": False}
        result = adapter.check_has_matching_templates("civil")
        assert result["has_folder"] is True
        assert result["has_document"] is False


# ── evidence_merge_usecase.py (MergeProgressReporter) ──────────────────────


class TestMergeProgressReporter:
    """MergeProgressReporter 节流逻辑。"""

    @patch("apps.documents.services.evidence.evidence_merge_usecase.time")
    @patch("apps.documents.models.EvidenceList")
    def test_report_updates_db(self, mock_model, mock_time) -> None:
        from apps.documents.services.evidence.evidence_merge_usecase import MergeProgressReporter

        mock_time.time.return_value = 1000.0
        reporter = MergeProgressReporter(list_id=1, min_interval_seconds=0.5)
        reporter.report(current=50, total=100, message="处理中")
        mock_model.objects.filter.assert_called_once_with(pk=1)

    @patch("apps.documents.services.evidence.evidence_merge_usecase.time")
    @patch("apps.documents.models.EvidenceList")
    def test_report_throttle_same_progress_within_interval(self, mock_model, mock_time) -> None:
        from apps.documents.services.evidence.evidence_merge_usecase import MergeProgressReporter

        mock_time.time.return_value = 1000.0
        reporter = MergeProgressReporter(list_id=1, min_interval_seconds=0.5)
        reporter.report(current=50, total=100, message="处理中")

        # 第二次同进度、间隔不够 → 不更新
        mock_time.time.return_value = 1000.3
        reporter.report(current=50, total=100, message="处理中")
        assert mock_model.objects.filter.call_count == 1

    @patch("apps.documents.services.evidence.evidence_merge_usecase.time")
    @patch("apps.documents.models.EvidenceList")
    def test_report_throttle_different_progress_updates(self, mock_model, mock_time) -> None:
        from apps.documents.services.evidence.evidence_merge_usecase import MergeProgressReporter

        mock_time.time.return_value = 1000.0
        reporter = MergeProgressReporter(list_id=1, min_interval_seconds=0.5)
        reporter.report(current=50, total=100, message="处理中")

        # 不同进度 → 即使间隔不够也更新
        mock_time.time.return_value = 1000.3
        reporter.report(current=60, total=100, message="处理中")
        assert mock_model.objects.filter.call_count == 2

    @patch("apps.documents.services.evidence.evidence_merge_usecase.time")
    @patch("apps.documents.models.EvidenceList")
    def test_report_throttle_same_progress_after_interval(self, mock_model, mock_time) -> None:
        from apps.documents.services.evidence.evidence_merge_usecase import MergeProgressReporter

        mock_time.time.return_value = 1000.0
        reporter = MergeProgressReporter(list_id=1, min_interval_seconds=0.5)
        reporter.report(current=50, total=100, message="处理中")

        # 同进度但间隔已过 → 更新
        mock_time.time.return_value = 1000.6
        reporter.report(current=50, total=100, message="处理中")
        assert mock_model.objects.filter.call_count == 2

    @patch("apps.documents.services.evidence.evidence_merge_usecase.time")
    @patch("apps.documents.models.EvidenceList")
    def test_report_zero_total(self, mock_model, mock_time) -> None:
        from apps.documents.services.evidence.evidence_merge_usecase import MergeProgressReporter

        mock_time.time.return_value = 1000.0
        reporter = MergeProgressReporter(list_id=1)
        reporter.report(current=0, total=0, message="准备中")
        mock_model.objects.filter.assert_called_once()


# ── generation_task_service.py ──────────────────────────────────────────────


class TestGenerationTaskService:
    """GenerationTaskService._to_dto() 和状态方法。"""

    def _make_service(self):
        from apps.documents.services.generation.generation_task_service import GenerationTaskService

        return GenerationTaskService()

    def _mock_task(self, **kwargs):
        defaults = {
            "pk": 42,
            "status": "processing",
            "created_at": "2026-01-01T00:00:00Z",
            "created_by_id": None,
            "result_file": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_to_dto_no_result_file(self) -> None:
        svc = self._make_service()
        task = self._mock_task(result_file=None)
        dto = svc._to_dto(task)
        assert dto.id == 42
        assert dto.document_name is None
        assert dto.document_url is None

    def test_to_dto_with_result_file(self) -> None:
        svc = self._make_service()
        result_file = SimpleNamespace(name="path/to/doc.pdf", url="http://example.com/doc.pdf")
        task = self._mock_task(result_file=result_file)
        dto = svc._to_dto(task)
        assert dto.document_name == "doc.pdf"
        assert dto.document_url == "http://example.com/doc.pdf"

    def test_to_dto_result_file_url_exception_fallback(self) -> None:
        svc = self._make_service()

        def raise_url():
            raise OSError("no url")

        result_file = MagicMock()
        result_file.name = "path/to/file.docx"
        type(result_file).url = property(lambda self: raise_url())
        task = self._mock_task(result_file=result_file)
        dto = svc._to_dto(task)
        assert dto.document_name == "file.docx"
        assert dto.document_url is not None
        assert "file.docx" in dto.document_url

    @patch("apps.documents.services.generation.generation_task_service.GenerationTask")
    def test_get_task_internal_returns_none(self, mock_model) -> None:
        svc = self._make_service()
        mock_model.objects.filter.return_value.first.return_value = None
        assert svc.get_task_internal(999) is None

    @patch("apps.documents.services.generation.generation_task_service.GenerationTask")
    def test_mark_task_failed_when_not_found(self, mock_model) -> None:
        svc = self._make_service()
        mock_model.objects.filter.return_value.first.return_value = None
        dto = svc.mark_task_failed_internal(task_id=999, error_message="err")
        assert dto.id == 999
        assert dto.status == "failed"

    @patch("apps.documents.services.generation.generation_task_service.GenerationTask")
    def test_mark_task_completed_when_not_found(self, mock_model) -> None:
        svc = self._make_service()
        mock_model.objects.filter.return_value.first.return_value = None
        dto = svc.mark_task_completed_internal(task_id=999, result_file="f", metadata_updates={})
        assert dto.id == 999
        assert dto.status == "failed"


# ── case_contract_query.py ─────────────────────────────────────────────────


class TestCaseContractQuery:
    """apps/documents/services/case_contract_query.py 查询函数。"""

    @patch("apps.documents.services.case_contract_query.Case")
    def test_get_case_or_none_found(self, mock_case_model) -> None:
        from apps.documents.services.case_contract_query import get_case_or_none

        mock_case_model.objects.filter.return_value.first.return_value = "case_obj"
        assert get_case_or_none(1) == "case_obj"

    @patch("apps.documents.services.case_contract_query.Case")
    def test_get_case_or_none_not_found(self, mock_case_model) -> None:
        from apps.documents.services.case_contract_query import get_case_or_none

        mock_case_model.objects.filter.return_value.first.return_value = None
        assert get_case_or_none(999) is None

    @patch("apps.documents.services.case_contract_query.Case")
    def test_get_case_contract_info(self, mock_case_model) -> None:
        from apps.documents.services.case_contract_query import get_case_contract_info

        expected = {"contract_id": 10, "contract__folder_binding__id": 20}
        mock_case_model.objects.filter.return_value.values.return_value.first.return_value = expected
        assert get_case_contract_info(1) == expected

    @patch("apps.documents.models.external_template.ExternalTemplate")
    @patch("apps.documents.models.DocumentTemplate")
    def test_get_active_template_found(self, mock_tpl_model, _) -> None:
        from apps.documents.services.case_contract_query import get_active_template_or_none

        mock_tpl_model.objects.filter.return_value.first.return_value = "tpl"
        assert get_active_template_or_none(1) == "tpl"

    @patch("apps.documents.models.external_template.ExternalTemplate")
    @patch("apps.documents.models.DocumentTemplate")
    def test_get_active_template_not_found(self, mock_tpl_model, _) -> None:
        from apps.documents.services.case_contract_query import get_active_template_or_none

        mock_tpl_model.objects.filter.return_value.first.return_value = None
        assert get_active_template_or_none(999) is None


# ── re-export compatibility ─────────────────────────────────────────────────


class TestDocumentsReExportCompatibility:
    """确保 re-export 文件正确透传。"""

    def test_evidence_storage_re_export(self) -> None:
        from apps.documents.services.evidence.evidence_storage import EvidenceFileStorage

        assert EvidenceFileStorage is not None

    def test_evidence_service_re_export(self) -> None:
        from apps.documents.services.evidence_service import EvidenceService

        assert EvidenceService is not None

    def test_folder_service_re_export(self) -> None:
        from apps.documents.services.folder_service import FolderTemplateService

        assert FolderTemplateService is not None

    def test_generation_composition_re_export(self) -> None:
        from apps.documents.services.generation.composition import build_authorization_material_generation_service

        assert callable(build_authorization_material_generation_service)

    def test_generation_schemas_re_export(self) -> None:
        from apps.documents.services.generation.schemas import ComplaintOutput, DefenseOutput, PartyInfo

        assert ComplaintOutput is not None
        assert DefenseOutput is not None
        assert PartyInfo is not None

    def test_tasks_re_export(self) -> None:
        from apps.documents.tasks import merge_evidence_pdf_task

        assert callable(merge_evidence_pdf_task)


# ── external_template/query_service.py ──────────────────────────────────────


class TestExternalTemplateQueryService:
    """apps/documents/services/external_template/query_service.py"""

    @patch("apps.documents.services.external_template.query_service.ExternalTemplate")
    def test_get_template_or_raise_found(self, mock_model) -> None:
        from apps.documents.services.external_template.query_service import get_template_or_raise

        mock_model.objects.get.return_value = "tpl"
        assert get_template_or_raise(1) == "tpl"
        mock_model.objects.get.assert_called_once_with(pk=1)

    @patch("apps.documents.services.external_template.query_service.ExternalTemplate")
    def test_get_template_or_raise_not_found(self, mock_model) -> None:
        from apps.documents.services.external_template.query_service import get_template_or_raise

        exc_cls = type("FakeDoesNotExist", (Exception,), {})
        mock_model.DoesNotExist = exc_cls
        mock_model.objects.get.side_effect = exc_cls("not found")
        with pytest.raises(exc_cls):
            get_template_or_raise(999)

    @patch("apps.documents.services.external_template.query_service.ExternalTemplateFieldMapping")
    def test_get_mappings_by_template(self, mock_model) -> None:
        from apps.documents.services.external_template.query_service import get_mappings_by_template

        mock_qs = MagicMock()
        mock_qs.order_by.return_value = ["m1", "m2"]
        mock_model.objects.filter.return_value = mock_qs
        result = get_mappings_by_template(1)
        assert result == ["m1", "m2"]
        mock_model.objects.filter.assert_called_once_with(template_id=1)
        mock_qs.order_by.assert_called_once_with("sort_order", "id")

    @patch("apps.documents.services.external_template.query_service.ExternalTemplateFieldMapping")
    def test_get_mapping_or_raise_found(self, mock_model) -> None:
        from apps.documents.services.external_template.query_service import get_mapping_or_raise

        mock_model.objects.get.return_value = "mapping"
        assert get_mapping_or_raise(1) == "mapping"

    @patch("apps.documents.services.external_template.query_service.ExternalTemplateFieldMapping")
    def test_get_mapping_or_raise_not_found(self, mock_model) -> None:
        from apps.documents.services.external_template.query_service import get_mapping_or_raise

        exc_cls = type("FakeDoesNotExist", (Exception,), {})
        mock_model.DoesNotExist = exc_cls
        mock_model.objects.get.side_effect = exc_cls("not found")
        with pytest.raises(exc_cls):
            get_mapping_or_raise(999)
