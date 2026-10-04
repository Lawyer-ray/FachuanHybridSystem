"""generation 服务批量补覆盖。

覆盖：litigation_generation_service、litigation_context_builder、
generation_task_service、generation/pipeline/context_builder、generation/pipeline/template_matcher。
LLM、模板渲染与 ORM 全部用替身。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException

GENERATION = "apps.documents.services.generation"
LITIGATION_PKG = "apps.documents.services.placeholders.litigation"


# ── LitigationContextBuilder ────────────────────────────────────────


class TestLitigationContextBuilderConvert:
    def _builder(self):
        from apps.documents.services.generation.litigation_context_builder import LitigationContextBuilder

        return LitigationContextBuilder()

    def test_empty_text(self):
        assert self._builder().convert_to_paragraphs("") == ""

    def test_crlf_and_lf_replaced(self):
        builder = self._builder()
        assert builder.convert_to_paragraphs("A\r\nB\nC") == "A\aB\aC"


class TestLitigationContextBuilderPromptData:
    def _builder(self):
        from apps.documents.services.generation.litigation_context_builder import LitigationContextBuilder

        return LitigationContextBuilder()

    def _patch_parties(self, plaintiff="原告甲", defendant="被告乙"):
        case_service = MagicMock()
        case_service.get_case_parties_by_legal_status_internal.side_effect = lambda case_id, legal_status: (
            [plaintiff] if legal_status == "plaintiff" else [defendant]
        )
        return patch(f"{GENERATION}.litigation_context_builder.get_case_service", return_value=case_service)

    def test_extract_complaint_prompt_data(self):
        case_dto = SimpleNamespace(id=1, cause_of_action="借款合同纠纷")
        with self._patch_parties():
            data = self._builder().extract_complaint_prompt_data(case_dto)
        assert data["cause_of_action"] == "借款合同纠纷"
        assert data["plaintiff"] == "原告甲"
        assert data["defendant"] == "被告乙"
        assert data["litigation_request"] == "请求依法判决"
        assert data["facts_and_reasons"] == "事实与理由待补充"

    def test_extract_defense_prompt_data_defaults(self):
        case_dto = SimpleNamespace(id=1, cause_of_action=None)
        case_service = MagicMock()
        case_service.get_case_parties_by_legal_status_internal.return_value = []  # 无当事人
        with patch(f"{GENERATION}.litigation_context_builder.get_case_service", return_value=case_service):
            data = self._builder().extract_defense_prompt_data(case_dto)
        assert data["cause_of_action"] == "民事纠纷"  # 空案由回退
        assert data["plaintiff"] == "未指定"  # 空列表回退
        assert data["defendant"] == "未指定"
        assert data["defense_opinion"] == "不同意原告的诉讼请求"

    def test_build_complaint_context_merges_llm_result(self):
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys as Keys

        enhanced = MagicMock()
        enhanced.build_context.return_value = {"基础": "上下文"}
        builder = self._builder()
        builder._enhanced_context_builder = enhanced
        case_dto = SimpleNamespace(id=1)
        llm_result = SimpleNamespace(litigation_request="请求一\r\n请求二", facts_and_reasons="事实\n理由")
        context = builder.build_complaint_context(case_dto=case_dto, llm_result=llm_result)

        assert context["基础"] == "上下文"
        assert context[Keys.VARIABLE_LITIGATION_REQUEST] == "请求一\a请求二"
        assert context[Keys.VARIABLE_FACTS_AND_REASONS] == "事实\a理由"
        call = enhanced.build_context.call_args
        assert call.args[0] == {"case_id": 1, "case_dto": case_dto}
        assert Keys.COMPLAINT_PARTY in call.kwargs["required_placeholders"]

    def test_build_defense_context_merges_llm_result(self):
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys as Keys

        enhanced = MagicMock()
        enhanced.build_context.return_value = {}
        builder = self._builder()
        builder._enhanced_context_builder = enhanced
        llm_result = SimpleNamespace(defense_opinion="全部不同意", defense_reasons="理由一\n理由二")
        context = builder.build_defense_context(case_dto=SimpleNamespace(id=1), llm_result=llm_result)

        assert context[Keys.VARIABLE_DEFENSE_OPINION] == "全部不同意"
        assert context[Keys.VARIABLE_DEFENSE_REASONS] == "理由一\a理由二"

    def test_enhanced_builder_lazy_load(self):
        from apps.documents.services.generation.litigation_context_builder import LitigationContextBuilder

        builder = LitigationContextBuilder()
        assert builder.enhanced_context_builder is not None


# ── LitigationGenerationService ─────────────────────────────────────


class TestLitigationGenerationServiceDelegation:
    def _svc(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        llm = MagicMock()
        return LitigationGenerationService(llm_generator=llm, context_builder=MagicMock()), llm

    def test_lazy_properties(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        assert svc.llm_generator is not None
        assert svc.context_builder is not None

    def test_generate_complaint_delegates(self):
        svc, llm = self._svc()
        llm.generate_complaint.return_value = "complaint-output"
        assert svc.generate_complaint({"k": "v"}) == "complaint-output"
        llm.generate_complaint.assert_called_once_with({"k": "v"})

    def test_generate_defense_delegates(self):
        svc, llm = self._svc()
        llm.generate_defense.return_value = "defense-output"
        assert svc.generate_defense({"k": "v"}) == "defense-output"
        llm.generate_defense.assert_called_once_with({"k": "v"})

    def test_template_paths_under_docx_root(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        svc = LitigationGenerationService()
        complaint_path = svc._complaint_template_path()
        defense_path = svc._defense_template_path()
        assert complaint_path.name == "1-起诉状.docx"
        assert defense_path.name == "1-答辩状.docx"


class TestLitigationGenerationServiceDocuments:
    def _svc(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        context_builder = MagicMock()
        context_builder.extract_complaint_prompt_data.return_value = {"plaintiff": "甲", "defendant": "乙"}
        context_builder.extract_defense_prompt_data.return_value = {"plaintiff": "甲", "defendant": "乙"}
        context_builder.build_complaint_context.return_value = {"占位": "值"}
        context_builder.build_defense_context.return_value = {"占位": "值"}
        return (
            LitigationGenerationService(llm_generator=MagicMock(), context_builder=context_builder),
            context_builder,
        )

    def test_case_not_found_raises(self):
        svc, _cb = self._svc()
        locator = MagicMock()
        locator.get_case_service.return_value.get_case_by_id_internal.return_value = None
        with patch(f"{GENERATION}.litigation_generation_service.ServiceLocator", locator):
            from apps.core.exceptions import NotFoundError

            with pytest.raises(NotFoundError):
                svc.generate_complaint_document(1)
            with pytest.raises(NotFoundError):
                svc.generate_defense_document(1)

    def test_generate_complaint_document_with_mocks(self):
        svc, cb = self._svc()
        locator = MagicMock()
        locator.get_case_service.return_value.get_case_by_id_internal.return_value = SimpleNamespace(id=1)
        with (
            patch(f"{GENERATION}.litigation_generation_service.ServiceLocator", locator),
            patch(f"{LITIGATION_PKG}.FilenameService") as mock_filename_svc,
            patch.object(svc, "_render_template", return_value=b"docx-bytes") as mock_render,
        ):
            mock_filename_svc.return_value.generate_complaint_filename.return_value = "起诉状（甲）V1.docx"
            filename, content = svc.generate_complaint_document(1, skip_llm=True)

        assert filename == "起诉状（甲）V1.docx"
        assert content == b"docx-bytes"
        cb.build_complaint_context.assert_called_once()
        mock_render.assert_called_once()

    def test_generate_defense_document_skips_llm_by_default(self):
        svc, _cb = self._svc()
        locator = MagicMock()
        locator.get_case_service.return_value.get_case_by_id_internal.return_value = SimpleNamespace(id=1)
        with (
            patch(f"{GENERATION}.litigation_generation_service.ServiceLocator", locator),
            patch(f"{LITIGATION_PKG}.FilenameService") as mock_filename_svc,
            patch.object(svc, "_render_template", return_value=b"docx"),
            patch.object(svc, "generate_defense") as mock_llm_defense,
        ):
            mock_filename_svc.return_value.generate_defense_filename.return_value = "答辩状.docx"
            svc.generate_defense_document(1)
        mock_llm_defense.assert_not_called()

    def test_generate_complaint_document_can_call_llm(self):
        svc, _cb = self._svc()
        locator = MagicMock()
        locator.get_case_service.return_value.get_case_by_id_internal.return_value = SimpleNamespace(id=1)
        with (
            patch(f"{GENERATION}.litigation_generation_service.ServiceLocator", locator),
            patch(f"{LITIGATION_PKG}.FilenameService") as mock_filename_svc,
            patch.object(svc, "_render_template", return_value=b"docx"),
            patch.object(svc, "generate_complaint", return_value="llm-output") as mock_llm,
        ):
            mock_filename_svc.return_value.generate_complaint_filename.return_value = "起诉状.docx"
            svc.generate_complaint_document(1, skip_llm=False)
        mock_llm.assert_called_once()


class TestLitigationGenerationServiceHelpers:
    def _svc(self):
        from apps.documents.services.generation.litigation_generation_service import LitigationGenerationService

        return LitigationGenerationService(llm_generator=MagicMock(), context_builder=MagicMock())

    def test_generate_filename_complaint_and_defense(self):
        svc = self._svc()
        with patch(f"{LITIGATION_PKG}.FilenameService") as mock_filename_svc:
            mock_filename_svc.return_value.generate_complaint_filename.return_value = "起诉状.docx"
            assert svc._generate_filename(1, "complaint") == "起诉状.docx"
        with patch(f"{LITIGATION_PKG}.FilenameService") as mock_filename_svc:
            mock_filename_svc.return_value.generate_defense_filename.return_value = "答辩状.docx"
            assert svc._generate_filename(1, "defense") == "答辩状.docx"

    def test_generate_filename_unknown_type_raises(self):
        with pytest.raises(ValidationException):
            self._svc()._generate_filename(1, "unknown")

    def test_mock_complaint_output(self):
        result = self._svc()._get_mock_complaint_output(
            {"cause_of_action": "借款纠纷", "plaintiff": "甲", "defendant": "乙"}
        )
        assert result.title == "借款纠纷起诉状"
        assert [p.name for p in result.parties] == ["甲", "乙"]
        assert "诉讼费用" in result.litigation_request
        assert result.evidence == ["借款合同", "转账记录", "催款记录"]

    def test_mock_defense_output_defaults(self):
        result = self._svc()._get_mock_defense_output({})
        assert result.title == "民事纠纷答辩状"
        assert result.defense_opinion.startswith("答辩人不同意")
        assert "驳回原告的全部诉讼请求" in result.defense_reasons

    def test_render_template_missing_file_raises(self, tmp_path):
        with pytest.raises(ValidationException, match="模板文件不存在"):
            self._svc()._render_template(tmp_path / "missing.docx", {})

    def test_render_template_render_error_wrapped(self, tmp_path):
        tpl = tmp_path / "tpl.docx"
        tpl.write_bytes(b"docx")
        with patch(f"{GENERATION}.pipeline.DocxRenderer") as mock_renderer:
            mock_renderer.return_value.render.side_effect = ValueError("boom")
            with pytest.raises(ValidationException, match="模板渲染失败"):
                self._svc()._render_template(tpl, {})

    def test_render_template_adds_year_when_missing(self, tmp_path):
        from datetime import date

        tpl = tmp_path / "tpl.docx"
        tpl.write_bytes(b"docx")
        with patch(f"{GENERATION}.pipeline.DocxRenderer") as mock_renderer:
            mock_renderer.return_value.render.return_value = b"rendered"
            result = self._svc()._render_template(tpl, {})
        assert result == b"rendered"
        context_passed = mock_renderer.return_value.render.call_args.args[1]
        assert context_passed["年份"] == str(date.today().year)


# ── GenerationTaskService ───────────────────────────────────────────


class TestGenerationTaskService:
    def _svc(self):
        from apps.documents.services.generation.generation_task_service import GenerationTaskService

        return GenerationTaskService()

    def _patch_task(self, task):
        manager = MagicMock()
        manager.filter.return_value.first.return_value = task
        return patch(f"{GENERATION}.generation_task_service.GenerationTask", objects=manager)

    def test_mark_task_completed(self):
        from apps.documents.models import GenerationStatus

        task = MagicMock()
        task.metadata = {"k": "v"}
        svc = self._svc()
        with self._patch_task(task):
            dto = svc.mark_task_completed_internal(task_id=1, result_file="files/x.docx", metadata_updates={"m": 1})
        assert dto.status == GenerationStatus.COMPLETED
        assert task.status == GenerationStatus.COMPLETED
        assert task.result_file == "files/x.docx"
        assert task.metadata == {"k": "v", "m": 1}
        task.save.assert_called_once()

    def test_mark_task_completed_missing_task(self):
        from apps.documents.models import GenerationStatus

        svc = self._svc()
        with self._patch_task(None):
            dto = svc.mark_task_completed_internal(task_id=9, result_file="f", metadata_updates={})
        assert dto.status == GenerationStatus.FAILED

    def test_mark_task_failed(self):
        from apps.documents.models import GenerationStatus

        task = MagicMock()
        svc = self._svc()
        with self._patch_task(task):
            dto = svc.mark_task_failed_internal(task_id=1, error_message="boom")
        assert dto.status == GenerationStatus.FAILED
        assert task.error_message == "boom"
        task.save.assert_called_once()

    def test_mark_task_failed_missing_task(self):
        from apps.documents.models import GenerationStatus

        svc = self._svc()
        with self._patch_task(None):
            dto = svc.mark_task_failed_internal(task_id=9, error_message="x")
        assert dto.status == GenerationStatus.FAILED

    def test_mark_task_failed_empty_message_coerced(self):
        task = MagicMock()
        svc = self._svc()
        with self._patch_task(task):
            svc.mark_task_failed_internal(task_id=1, error_message=None)
        assert task.error_message == ""

    def test_get_task_internal_found(self):
        task = MagicMock(pk=3)
        svc = self._svc()
        with self._patch_task(task):
            dto = svc.get_task_internal(3)
        assert dto is not None and dto.id == 3

    def test_get_task_internal_missing(self):
        svc = self._svc()
        with self._patch_task(None):
            assert svc.get_task_internal(404) is None

    def test_to_dto_without_result_file(self):
        task = MagicMock(pk=1, result_file=None, created_by_id=2)
        dto = self._svc()._to_dto(task)
        assert dto.document_name is None
        assert dto.document_url is None

    def test_to_dto_with_result_file(self):
        task = MagicMock(pk=1, created_by_id=None)
        task.result_file = SimpleNamespace(name="media/docs/报告.docx", url="/media/media/docs/报告.docx")
        dto = self._svc()._to_dto(task)
        assert dto.document_name == "报告.docx"
        assert dto.document_url == "/media/media/docs/报告.docx"

    def test_to_dto_url_error_falls_back_to_media_url(self):
        class _FakeFieldFile:
            name = "docs/报告.docx"

            @property
            def url(self):
                raise RuntimeError("no url")

        task = MagicMock(pk=1)
        task.result_file = _FakeFieldFile()
        dto = self._svc()._to_dto(task)
        assert dto.document_name == "报告.docx"
        assert dto.document_url == "/media/docs/报告.docx"


# ── pipeline/context_builder ────────────────────────────────────────


class TestPipelineContextBuilder:
    def _builder(self):
        from apps.documents.services.generation.pipeline.context_builder import PipelineContextBuilder

        return PipelineContextBuilder()

    def test_build_contract_context(self):
        placeholder_cb_pkg = "apps.documents.services.placeholders"
        enhanced = MagicMock()
        enhanced.build_context.return_value = {"合同": "上下文"}
        with patch(f"{placeholder_cb_pkg}.EnhancedContextBuilder", return_value=enhanced):
            result = self._builder().build_contract_context("contract", split_fee=False)
        assert result == {"合同": "上下文"}
        enhanced.build_context.assert_called_once_with({"contract": "contract", "split_fee": False})

    def test_build_supplementary_agreement_context(self):
        target = "apps.documents.services.placeholders.context_builder.EnhancedContextBuilder"
        enhanced = MagicMock()
        enhanced.build_context.return_value = {"补充协议": "上下文"}
        with patch(target, return_value=enhanced):
            result = self._builder().build_supplementary_agreement_context(
                contract="c",
                supplementary_agreement="a",
                agreement_principals=[],
                contract_principals=[],
                agreement_opposing=[],
            )
        assert result == {"补充协议": "上下文"}

    def test_build_archive_context(self):
        target = "apps.documents.services.placeholders.context_builder.EnhancedContextBuilder"
        enhanced = MagicMock()
        enhanced.build_context.return_value = {"归档": "上下文"}
        with patch(target, return_value=enhanced):
            result = self._builder().build_archive_context("contract", "case")
        assert result == {"归档": "上下文"}


# ── pipeline/template_matcher ───────────────────────────────────────


class TestPipelineTemplateMatcher:
    def _matcher(self):
        from apps.documents.services.generation.pipeline.template_matcher import TemplateMatcher

        return TemplateMatcher()

    def test_match_contract_template(self):
        tpl = MagicMock()
        tpl.contract_types = ["civil"]
        manager = MagicMock()
        manager.filter.return_value.filter.return_value = [tpl]
        with patch("apps.documents.models.DocumentTemplate", objects=manager):
            assert self._matcher().match_contract_template("civil") is tpl

    def test_match_contract_template_all_wildcard(self):
        tpl = MagicMock()
        tpl.contract_types = ["all"]
        manager = MagicMock()
        manager.filter.return_value.filter.return_value = [tpl]
        with patch("apps.documents.models.DocumentTemplate", objects=manager):
            assert self._matcher().match_contract_template("criminal") is tpl

    def test_match_contract_template_no_match(self):
        tpl = MagicMock()
        tpl.contract_types = ["civil"]
        manager = MagicMock()
        manager.filter.return_value.filter.return_value = [tpl]
        with patch("apps.documents.models.DocumentTemplate", objects=manager):
            assert self._matcher().match_contract_template("labor") is None

    def test_match_contract_template_empty_types_no_match(self):
        tpl = MagicMock()
        tpl.contract_types = []
        manager = MagicMock()
        manager.filter.return_value.filter.return_value = [tpl]
        with patch("apps.documents.models.DocumentTemplate", objects=manager):
            assert self._matcher().match_contract_template("civil") is None

    def test_match_supplementary_agreement_template(self):
        tpl = MagicMock()
        tpl.contract_types = ["civil"]
        manager = MagicMock()
        manager.filter.return_value = [tpl]
        with patch("apps.documents.models.DocumentTemplate", objects=manager):
            assert self._matcher().match_supplementary_agreement_template("civil") is tpl

    def test_match_supplementary_agreement_template_no_match(self):
        manager = MagicMock()
        manager.filter.return_value = []
        with patch("apps.documents.models.DocumentTemplate", objects=manager):
            assert self._matcher().match_supplementary_agreement_template("civil") is None

    def test_match_folder_template(self):
        tpl = MagicMock()
        tpl.contract_types = ["civil"]
        manager = MagicMock()
        manager.filter.return_value = [tpl]
        with patch("apps.documents.models.FolderTemplate", objects=manager):
            assert self._matcher().match_folder_template("civil") is tpl

    def test_match_folder_template_no_match(self):
        manager = MagicMock()
        manager.filter.return_value = []
        with patch("apps.documents.models.FolderTemplate", objects=manager):
            assert self._matcher().match_folder_template("civil") is None
