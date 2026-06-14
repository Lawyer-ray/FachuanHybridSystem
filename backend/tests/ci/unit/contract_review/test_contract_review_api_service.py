"""contract_review 模块 API/Repository/Admin/Service 测试

覆盖文件:
- apps/contract_review/api/review_api.py
- apps/contract_review/api/format_api.py
- apps/contract_review/repositories/review_task_repository.py
- apps/contract_review/models/review_task.py
- apps/contract_review/models/format_normalize.py
- apps/contract_review/services/exceptions.py
- apps/contract_review/services/review/review_service.py
- apps/contract_review/services/review/contract_reviewer.py
- apps/contract_review/services/review/party_identifier.py
- apps/contract_review/services/review/typo_checker.py
- apps/contract_review/admin/review_task_admin.py
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ==================== Exceptions ====================


class TestContractReviewExceptions:
    """异常类基础测试"""

    def test_contract_review_error(self):
        from apps.contract_review.services.exceptions import ContractReviewError

        err = ContractReviewError("test error")
        assert str(err) == "test error"
        assert isinstance(err, Exception)

    def test_extraction_error_is_subclass(self):
        from apps.contract_review.services.exceptions import ContractReviewError, ExtractionError

        err = ExtractionError("extraction failed")
        assert isinstance(err, ContractReviewError)

    def test_parsing_error_is_subclass(self):
        from apps.contract_review.services.exceptions import ContractReviewError, ParsingError

        err = ParsingError("parsing failed")
        assert isinstance(err, ContractReviewError)


# ==================== Models ====================


class TestReviewTaskModel:
    """ReviewTask 模型测试"""

    def test_task_status_choices(self):
        from apps.contract_review.models.review_task import TaskStatus

        assert TaskStatus.UPLOADED == "uploaded"
        assert TaskStatus.PARTIES_IDENTIFIED == "parties_identified"
        assert TaskStatus.CONFIRMED == "confirmed"
        assert TaskStatus.PROCESSING == "processing"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.EXTRACTION_FAILED == "extraction_failed"

    def test_process_step_choices(self):
        from apps.contract_review.models.review_task import ProcessStep

        assert ProcessStep.TITLE_EXTRACTION == "title_extraction"
        assert ProcessStep.TYPO_CHECK == "typo_check"
        assert ProcessStep.CONTRACT_REVIEW == "contract_review"
        assert ProcessStep.FORMAT_DOCUMENT == "format_document"
        assert ProcessStep.PAGE_NUMBERING == "page_numbering"
        assert ProcessStep.HEADING_NUMBERING == "heading_numbering"

    def test_represented_party_choices(self):
        from apps.contract_review.models.review_task import RepresentedParty

        assert RepresentedParty.PARTY_A == "party_a"
        assert RepresentedParty.PARTY_B == "party_b"
        assert RepresentedParty.PARTY_C == "party_c"
        assert RepresentedParty.PARTY_D == "party_d"

    def test_format_normalize_proxy_model(self):
        from apps.contract_review.models.format_normalize import FormatNormalize

        assert FormatNormalize._meta.proxy is True
        assert FormatNormalize._meta.app_label == "contract_review"


# ==================== Schemas ====================


class TestReviewSchemas:
    """Schema 序列化测试"""

    def test_confirm_party_in(self):
        from apps.contract_review.schemas.review_schemas import ConfirmPartyIn

        data = ConfirmPartyIn(represented_party="party_a", reviewer_name="律师A")
        assert data.represented_party == "party_a"
        assert data.reviewer_name == "律师A"
        assert data.selected_steps == []
        assert data.party_a == ""

    def test_task_created_out(self):
        from apps.contract_review.schemas.review_schemas import TaskCreatedOut

        data = TaskCreatedOut(
            task_id=uuid.uuid4(),
            status="uploaded",
            contract_title="Test",
            parties={"party_a": "A"},
        )
        assert data.status == "uploaded"
        assert data.parties == {"party_a": "A"}

    def test_task_status_out(self):
        from apps.contract_review.schemas.review_schemas import TaskStatusOut

        data = TaskStatusOut(
            task_id=uuid.uuid4(),
            status="completed",
            current_step="done",
            error_message=None,
            output_filename="result.docx",
        )
        assert data.status == "completed"
        assert data.output_filename == "result.docx"

    def test_format_normalize_in(self):
        from apps.contract_review.schemas.format_schemas import FormatNormalizeIn

        tid = uuid.uuid4()
        data = FormatNormalizeIn(task_id=tid)
        assert data.task_id == tid
        assert data.reference_file is None

    def test_format_normalize_out(self):
        from apps.contract_review.schemas.format_schemas import FormatNormalizeOut

        data = FormatNormalizeOut(
            task_id=uuid.uuid4(),
            status="success",
            output_file="/path/to/file",
            message="done",
        )
        assert data.status == "success"


# ==================== Repository ====================


class TestReviewTaskRepository:
    """ReviewTaskRepository 测试"""

    @pytest.fixture
    def repo(self):
        from apps.contract_review.repositories.review_task_repository import ReviewTaskRepository

        return ReviewTaskRepository()

    @pytest.fixture
    def user(self, db):
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="Repo测试律所")
        return Lawyer.objects.create_user(
            username="repouser",
            password="testpass123",  # pragma: allowlist secret
            law_firm=firm,
        )

    def test_create(self, repo, user):
        task = repo.create(
            user=user,
            original_file="/tmp/test.docx",
            status="uploaded",
        )
        assert task.pk is not None
        assert task.original_file == "/tmp/test.docx"

    def test_get_by_id(self, repo, user):
        task = repo.create(user=user, original_file="/tmp/a.docx", status="uploaded")
        result = repo.get_by_id(task.id)
        assert result is not None
        assert result.id == task.id

    def test_get_by_id_not_found(self, repo, db):
        result = repo.get_by_id(uuid.uuid4())
        assert result is None

    def test_get_by_id_required(self, repo, user):
        task = repo.create(user=user, original_file="/tmp/b.docx", status="uploaded")
        result = repo.get_by_id_required(task.id)
        assert result.id == task.id

    def test_get_by_id_required_not_found(self, repo, db):
        from apps.contract_review.models import ReviewTask

        with pytest.raises(ReviewTask.DoesNotExist):
            repo.get_by_id_required(uuid.uuid4())

    def test_update(self, repo, user):
        task = repo.create(user=user, original_file="/tmp/c.docx", status="uploaded")
        result = repo.update(task.id, status="completed")
        assert result is not None
        assert result.status == "completed"

    def test_filter_by_user(self, repo, user):
        repo.create(user=user, original_file="/tmp/d.docx", status="uploaded")
        qs = repo.filter_by_user(user)
        assert qs.count() >= 1

    def test_filter_by_status(self, repo, user):
        repo.create(user=user, original_file="/tmp/e.docx", status="uploaded")
        qs = repo.filter_by_status("uploaded")
        assert qs.count() >= 1

    def test_delete_by_id(self, repo, user):
        task = repo.create(user=user, original_file="/tmp/f.docx", status="uploaded")
        count, _ = repo.delete_by_id(task.id)
        assert count == 1
        assert repo.get_by_id(task.id) is None

    def test_delete_many(self, repo, user):
        t1 = repo.create(user=user, original_file="/tmp/g1.docx", status="uploaded")
        t2 = repo.create(user=user, original_file="/tmp/g2.docx", status="uploaded")
        count, _ = repo.delete_many([t1.id, t2.id])
        assert count == 2

    def test_exists(self, repo, user):
        task = repo.create(user=user, original_file="/tmp/h.docx", status="uploaded")
        assert repo.exists(task.id) is True
        assert repo.exists(uuid.uuid4()) is False


# ==================== ReviewService ====================


class TestReviewService:
    """ReviewService 核心逻辑测试"""

    @pytest.fixture
    def service(self):
        from apps.contract_review.services.review.review_service import ReviewService

        return ReviewService()

    @pytest.fixture
    def user(self, db):
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="Service测试律所")
        return Lawyer.objects.create_user(
            username="serviceuser",
            password="testpass123",  # pragma: allowlist secret
            law_firm=firm,
        )

    def test_upload_contract_non_docx_raises(self, service):
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        mock_user = MagicMock()
        from apps.contract_review.services.exceptions import ContractReviewError

        with pytest.raises(ContractReviewError, match=r"仅支持 \.docx"):
            service.upload_contract(mock_file, mock_user)

    @patch("apps.contract_review.services.review.review_service.Document")
    @patch("apps.contract_review.services.review.review_service.TitleExtractor")
    @patch("apps.contract_review.services.review.review_service.PartyIdentifier")
    @patch("apps.contract_review.services.review.review_service.ContentExtractor")
    @patch("apps.contract_review.services.review.review_service.settings")
    def test_upload_contract_success(
        self, mock_settings, mock_extractor_cls, mock_party_id_cls,
        mock_title_extractor_cls, mock_doc_cls, service, user
    ):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_settings.MEDIA_ROOT = tmpdir

            mock_file = MagicMock()
            mock_file.name = "contract.docx"
            mock_file.chunks.return_value = [b"fake docx content"]

            mock_extractor = MagicMock()
            mock_extractor.extract_paragraphs.return_value = ["甲方：A公司", "乙方：B公司"]
            mock_extractor_cls.return_value = mock_extractor

            mock_identifier = MagicMock()
            mock_identifier.identify_parties.return_value = {"party_a": "A公司", "party_b": "B公司"}
            mock_party_id_cls.return_value = mock_identifier

            mock_title_ext = MagicMock()
            mock_title_ext.extract_title.return_value = "测试合同"
            mock_title_extractor_cls.return_value = mock_title_ext

            task = service.upload_contract(mock_file, user, model_name="gpt-4")
            assert task.contract_title == "测试合同"
            assert task.party_a == "A公司"

    @patch("apps.contract_review.services.review.review_service.PartyIdentifier")
    @patch("apps.contract_review.services.review.review_service.ContentExtractor")
    @patch("apps.contract_review.services.review.review_service.settings")
    def test_upload_contract_extraction_error(self, mock_settings, mock_extractor_cls, mock_party_id_cls, service, user):
        from apps.contract_review.services.exceptions import ExtractionError

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_settings.MEDIA_ROOT = tmpdir

            mock_file = MagicMock()
            mock_file.name = "bad.docx"
            mock_file.chunks.return_value = [b"content"]

            mock_extractor = MagicMock()
            mock_extractor.extract_paragraphs.side_effect = ExtractionError("extraction failed")
            mock_extractor_cls.return_value = mock_extractor

            task = service.upload_contract(mock_file, user)
            assert task.status == "extraction_failed"

    def test_confirm_party_invalid_status(self, service):
        from apps.contract_review.services.exceptions import ContractReviewError

        mock_task = SimpleNamespace(status="completed")
        service._repository = MagicMock()
        service._repository.get_by_id_required.return_value = mock_task

        with pytest.raises(ContractReviewError, match="不允许确认代表方"):
            service.confirm_party(uuid.uuid4(), "party_a", MagicMock())

    @patch("apps.core.tasking.submit_task")
    def test_confirm_party_success(self, mock_submit, service):
        mock_task = SimpleNamespace(status="parties_identified")
        service._repository = MagicMock()
        service._repository.get_by_id_required.return_value = mock_task
        service._repository.get_by_id.return_value = mock_task

        result = service.confirm_party(
            uuid.uuid4(), "party_a", MagicMock(),
            reviewer_name="律师", selected_steps=["typo_check"],
        )
        assert result == mock_task
        service._repository.update.assert_called_once()
        mock_submit.assert_called_once()

    def test_get_task_status(self, service):
        mock_task = MagicMock()
        service._repository = MagicMock()
        service._repository.get_by_id_required.return_value = mock_task
        result = service.get_task_status(uuid.uuid4())
        assert result == mock_task

    def test_get_result_file_success(self, service):
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"test")
            tmp_path = f.name
        try:
            mock_task = SimpleNamespace(status="completed", output_file=tmp_path)
            service._repository = MagicMock()
            service._repository.get_by_id_required.return_value = mock_task
            result = service.get_result_file(uuid.uuid4())
            assert result.exists()
        finally:
            os.unlink(tmp_path)

    def test_get_result_file_not_completed(self, service):
        from apps.contract_review.services.exceptions import ContractReviewError

        mock_task = SimpleNamespace(status="processing", output_file="")
        service._repository = MagicMock()
        service._repository.get_by_id_required.return_value = mock_task

        with pytest.raises(ContractReviewError, match="任务尚未完成"):
            service.get_result_file(uuid.uuid4())

    def test_get_result_file_not_exists(self, service):
        from apps.contract_review.services.exceptions import ContractReviewError

        mock_task = SimpleNamespace(status="completed", output_file="/nonexistent/file.docx")
        service._repository = MagicMock()
        service._repository.get_by_id_required.return_value = mock_task

        with pytest.raises(ContractReviewError, match="结果文件不存在"):
            service.get_result_file(uuid.uuid4())

    def test_get_original_file_not_exists(self, service):
        from apps.contract_review.services.exceptions import ContractReviewError

        mock_task = SimpleNamespace(original_file="/nonexistent.docx")
        service._repository = MagicMock()
        service._repository.get_by_id_required.return_value = mock_task

        with pytest.raises(ContractReviewError, match="原始文件不存在"):
            service.get_original_file(uuid.uuid4())


# ==================== PartyIdentifier ====================


class TestPartyIdentifier:
    """PartyIdentifier 正则识别测试"""

    def test_identify_standard_format(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier

        paragraphs = [
            "合同编号：2024-001",
            "甲方：北京科技有限公司",
            "乙方：上海贸易有限公司",
        ]
        result = PartyIdentifier().identify_parties(paragraphs)
        assert result.get("party_a") == "北京科技有限公司"
        assert result.get("party_b") == "上海贸易有限公司"

    def test_identify_abbrev_format(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier

        paragraphs = [
            "甲方：北京科技有限公司（以下简称甲方）与上海贸易有限公司（以下简称乙方）签订本合同"
        ]
        result = PartyIdentifier().identify_parties(paragraphs)
        assert "party_a" in result
        assert "party_b" in result

    def test_identify_empty_paragraphs(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier

        result = PartyIdentifier().identify_parties([])
        assert result == {}

    def test_identify_no_parties(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier

        result = PartyIdentifier().identify_parties(["这是一段普通文字，没有当事人信息"])
        assert result == {}

    def test_identify_four_parties(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier

        paragraphs = [
            "甲方：A公司",
            "乙方：B公司",
            "丙方：C公司",
            "丁方：D公司",
        ]
        result = PartyIdentifier().identify_parties(paragraphs)
        assert result.get("party_a") == "A公司"
        assert result.get("party_b") == "B公司"
        assert result.get("party_c") == "C公司"
        assert result.get("party_d") == "D公司"

    def test_find_party_method(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier, _PARTY_PATTERNS

        result = PartyIdentifier._find_party("甲方：测试公司", _PARTY_PATTERNS["party_a"])
        assert result == "测试公司"

    def test_find_party_no_match(self):
        from apps.contract_review.services.review.party_identifier import PartyIdentifier, _PARTY_PATTERNS

        result = PartyIdentifier._find_party("无匹配文字", _PARTY_PATTERNS["party_a"])
        assert result == ""


# ==================== ContractReviewer ====================


class TestContractReviewer:
    """ContractReviewer LLM 交互测试"""

    def _make_reviewer(self):
        from apps.contract_review.services.review.contract_reviewer import ContractReviewer

        mock_llm = MagicMock()
        return ContractReviewer(mock_llm), mock_llm

    def test_review_contract_success(self):
        reviewer, mock_llm = self._make_reviewer()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps([
            {"original": "旧文本", "suggested": "新文本", "reason": "风险", "paragraph_index": 0}
        ])
        mock_llm.complete.return_value = mock_resp

        results = reviewer.review_contract(["旧文本"], "party_a", "A公司", "B公司")
        assert len(results) == 1
        assert results[0].original == "旧文本"
        assert results[0].suggested == "新文本"

    def test_review_contract_llm_error(self):
        reviewer, mock_llm = self._make_reviewer()
        mock_llm.complete.side_effect = Exception("LLM down")

        results = reviewer.review_contract(["text"], "party_a", "A", "B")
        assert results == []

    def test_review_contract_empty_response(self):
        reviewer, mock_llm = self._make_reviewer()
        mock_resp = MagicMock()
        mock_resp.content = "[]"
        mock_llm.complete.return_value = mock_resp

        results = reviewer.review_contract(["text"], "party_a", "A", "B")
        assert results == []

    def test_generate_report_success(self):
        reviewer, mock_llm = self._make_reviewer()
        mock_resp = MagicMock()
        mock_resp.content = "# 审查报告\n\n没有发现问题"
        mock_llm.complete.return_value = mock_resp

        report = reviewer.generate_report(["合同正文"], "party_a", "A公司", "B公司")
        assert "审查报告" in report

    def test_generate_report_llm_error(self):
        reviewer, mock_llm = self._make_reviewer()
        mock_llm.complete.side_effect = Exception("LLM error")

        report = reviewer.generate_report(["text"], "party_a", "A", "B")
        assert report == ""

    def test_parse_revision_response_markdown_block(self):
        from apps.contract_review.services.review.contract_reviewer import ContractReviewer

        text = '```json\n[{"original": "a", "suggested": "b", "reason": "r", "paragraph_index": 0}]\n```'
        results = ContractReviewer._parse_revision_response(text)
        assert len(results) == 1

    def test_parse_revision_response_invalid_json(self):
        from apps.contract_review.services.review.contract_reviewer import ContractReviewer

        results = ContractReviewer._parse_revision_response("not json at all")
        assert results == []

    def test_parse_revision_response_not_list(self):
        from apps.contract_review.services.review.contract_reviewer import ContractReviewer

        results = ContractReviewer._parse_revision_response('{"key": "value"}')
        assert results == []

    def test_parse_revision_response_missing_fields(self):
        from apps.contract_review.services.review.contract_reviewer import ContractReviewer

        results = ContractReviewer._parse_revision_response('[{"original": "a"}]')
        assert results == []

    def test_build_revision_prompt(self):
        from apps.contract_review.services.review.contract_reviewer import ContractReviewer

        prompt = ContractReviewer._build_revision_prompt("text", "party_a", "A公司", "B公司")
        assert "甲方" in prompt
        assert "A公司" in prompt

    def test_build_report_prompt(self):
        from apps.contract_review.services.review.contract_reviewer import ContractReviewer

        prompt = ContractReviewer._build_report_prompt("text", "party_b", "A公司", "B公司")
        assert "乙方" in prompt


# ==================== TypoChecker ====================


class TestTypoChecker:
    """TypoChecker 测试"""

    def _make_checker(self):
        from apps.contract_review.services.review.typo_checker import TypoChecker

        mock_llm = MagicMock()
        return TypoChecker(mock_llm), mock_llm

    def test_check_typos_single_batch(self):
        checker, mock_llm = self._make_checker()
        mock_resp = MagicMock()
        mock_resp.content = json.dumps([
            {"original": "错字", "corrected": "正确", "paragraph_index": 0}
        ])
        mock_llm.complete.return_value = mock_resp

        results = checker.check_typos(["文本含错字"], model_name="gpt-4")
        assert len(results) == 1
        assert results[0].corrected == "正确"

    def test_check_typos_empty_paragraphs(self):
        checker, _ = self._make_checker()
        results = checker.check_typos([])
        assert results == []

    def test_check_typos_multiple_batches(self):
        checker, mock_llm = self._make_checker()
        paragraphs = [f"段落{i}" for i in range(50)]
        mock_resp = MagicMock()
        mock_resp.content = "[]"
        mock_llm.complete.return_value = mock_resp

        results = checker.check_typos(paragraphs)
        assert isinstance(results, list)

    def test_parse_llm_response_markdown(self):
        from apps.contract_review.services.review.typo_checker import TypoChecker

        text = '```json\n[{"original": "a", "corrected": "b", "paragraph_index": 1}]\n```'
        results = TypoChecker._parse_llm_response(text)
        assert len(results) == 1

    def test_parse_llm_response_invalid(self):
        from apps.contract_review.services.review.typo_checker import TypoChecker

        results = TypoChecker._parse_llm_response("invalid")
        assert results == []

    def test_parse_llm_response_not_list(self):
        from apps.contract_review.services.review.typo_checker import TypoChecker

        results = TypoChecker._parse_llm_response('{"a": 1}')
        assert results == []

    def test_build_prompt(self):
        from apps.contract_review.services.review.typo_checker import TypoChecker

        prompt = TypoChecker._build_prompt("测试文本")
        assert "错别字" in prompt
        assert "测试文本" in prompt


# ==================== API - _check_task_access ====================


class TestCheckTaskAccess:
    """review_api._check_task_access 测试"""

    def test_none_user(self):
        from apps.contract_review.api.review_api import _check_task_access

        task = MagicMock()
        assert _check_task_access(task, None) is False

    def test_superuser(self):
        from apps.contract_review.api.review_api import _check_task_access

        task = MagicMock()
        user = MagicMock()
        user.is_superuser = True
        assert _check_task_access(task, user) is True

    def test_same_user(self):
        from apps.contract_review.api.review_api import _check_task_access

        user = MagicMock()
        user.is_superuser = False
        user.id = 1
        task = MagicMock()
        task.user_id = 1
        assert _check_task_access(task, user) is True

    def test_different_user(self):
        from apps.contract_review.api.review_api import _check_task_access

        user = MagicMock()
        user.is_superuser = False
        user.id = 2
        task = MagicMock()
        task.user_id = 1
        assert _check_task_access(task, user) is False


class TestFormatApiCheckTaskAccess:
    """format_api._check_task_access 测试"""

    def test_none_user(self):
        from apps.contract_review.api.format_api import _check_task_access

        task = MagicMock()
        assert _check_task_access(task, None) is False

    def test_superuser(self):
        from apps.contract_review.api.format_api import _check_task_access

        task = MagicMock()
        user = MagicMock()
        user.is_superuser = True
        assert _check_task_access(task, user) is True

    def test_same_user(self):
        from apps.contract_review.api.format_api import _check_task_access

        user = MagicMock()
        user.is_superuser = False
        user.id = 1
        task = MagicMock()
        task.user_id = 1
        assert _check_task_access(task, user) is True

    def test_different_user(self):
        from apps.contract_review.api.format_api import _check_task_access

        user = MagicMock()
        user.is_superuser = False
        user.id = 2
        task = MagicMock()
        task.user_id = 1
        assert _check_task_access(task, user) is False


# ==================== Review API endpoints ====================


class TestReviewApiUpload:
    """upload_contract API 测试"""

    @patch("apps.contract_review.api.review_api._get_review_service")
    def test_upload_contract(self, mock_get_svc):
        from apps.contract_review.api.review_api import upload_contract

        mock_svc = MagicMock()
        mock_task = MagicMock()
        mock_task.id = uuid.uuid4()
        mock_task.status = "parties_identified"
        mock_task.contract_title = "合同"
        mock_task.party_a = "A公司"
        mock_task.party_b = "B公司"
        mock_task.party_c = ""
        mock_task.party_d = ""
        mock_svc.upload_contract.return_value = mock_task
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        result = upload_contract(request, MagicMock(), model_name="gpt-4")
        assert result["task_id"] == mock_task.id
        assert result["status"] == "parties_identified"
        assert "party_a" in result["parties"]


class TestReviewApiConfirmParty:
    """confirm_party API 测试"""

    @patch("apps.contract_review.api.review_api._get_review_service")
    def test_confirm_party_success(self, mock_get_svc):
        from apps.contract_review.api.review_api import confirm_party
        from apps.contract_review.schemas.review_schemas import ConfirmPartyIn

        mock_svc = MagicMock()
        mock_task = MagicMock()
        mock_task.id = uuid.uuid4()
        mock_task.status = "processing"
        mock_task.current_step = "review"
        mock_task.error_message = ""
        mock_task.user_id = 1

        mock_svc.get_task_status.return_value = mock_task
        mock_svc.confirm_party.return_value = mock_task
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = True

        payload = ConfirmPartyIn(represented_party="party_a")
        result = confirm_party(request, uuid.uuid4(), payload)
        assert result["task_id"] == mock_task.id


class TestReviewApiGetStatus:
    """get_task_status API 测试"""

    @patch("apps.contract_review.api.review_api._get_review_service")
    def test_get_status_success(self, mock_get_svc):
        from apps.contract_review.api.review_api import get_task_status

        mock_svc = MagicMock()
        mock_task = MagicMock()
        mock_task.id = uuid.uuid4()
        mock_task.status = "completed"
        mock_task.current_step = ""
        mock_task.error_message = ""
        mock_task.output_file = "/path/to/output.docx"
        mock_task.user_id = 1
        mock_svc.get_task_status.return_value = mock_task
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = True

        result = get_task_status(request, uuid.uuid4())
        assert result["status"] == "completed"
        assert result["output_filename"] == "output.docx"

    @patch("apps.contract_review.api.review_api._get_review_service")
    def test_get_status_no_output(self, mock_get_svc):
        from apps.contract_review.api.review_api import get_task_status

        mock_svc = MagicMock()
        mock_task = MagicMock()
        mock_task.id = uuid.uuid4()
        mock_task.status = "processing"
        mock_task.current_step = "review"
        mock_task.error_message = ""
        mock_task.output_file = ""
        mock_task.user_id = 1
        mock_svc.get_task_status.return_value = mock_task
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = True

        result = get_task_status(request, uuid.uuid4())
        assert result["output_filename"] is None


class TestReviewApiGetModels:
    """get_models API 测试"""

    @patch("apps.contract_review.api.review_api._get_model_list_service")
    def test_get_models(self, mock_get_svc):
        from apps.contract_review.api.review_api import get_models

        mock_svc = MagicMock()
        mock_result = MagicMock()
        mock_result.models = ["gpt-4", "claude-3"]
        mock_result.is_fallback = False
        mock_result.error_message = None
        mock_svc.get_result.return_value = mock_result
        mock_get_svc.return_value = mock_svc

        request = MagicMock()
        result = get_models(request)
        assert "models" in result
        assert result["models"] == ["gpt-4", "claude-3"]


# ==================== Format API ====================


class TestFormatApiNormalize:
    """normalize_format API 测试"""

    @patch("apps.contract_review.api.format_api.ReviewTask")
    def test_task_not_found(self, mock_model):
        from apps.contract_review.api.format_api import normalize_format
        from apps.contract_review.schemas.format_schemas import FormatNormalizeIn

        mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_model.objects.get.side_effect = mock_model.DoesNotExist

        request = MagicMock()
        payload = FormatNormalizeIn(task_id=uuid.uuid4())
        result = normalize_format(request, payload)
        assert result["status"] == "failed"
        assert "不存在" in result["message"]

    @patch("apps.contract_review.api.format_api.ReviewTask")
    def test_no_permission(self, mock_model):
        from apps.contract_review.api.format_api import normalize_format
        from apps.contract_review.schemas.format_schemas import FormatNormalizeIn

        mock_task = MagicMock()
        mock_task.user_id = 1
        mock_model.objects.get.return_value = mock_task

        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = False
        request.user.id = 2

        payload = FormatNormalizeIn(task_id=uuid.uuid4())
        result = normalize_format(request, payload)
        assert result["status"] == "failed"
        assert "无权" in result["message"]

    @patch("apps.contract_review.api.format_api.ReviewTask")
    def test_no_original_file(self, mock_model):
        from apps.contract_review.api.format_api import normalize_format
        from apps.contract_review.schemas.format_schemas import FormatNormalizeIn

        mock_task = MagicMock()
        mock_task.user_id = 1
        mock_task.original_file = ""
        mock_model.objects.get.return_value = mock_task

        request = MagicMock()
        request.user = MagicMock()
        request.user.is_superuser = True

        payload = FormatNormalizeIn(task_id=uuid.uuid4())
        result = normalize_format(request, payload)
        assert result["status"] == "failed"
        assert "原始文件不存在" in result["message"]


class TestFormatApiDownloadNormalized:
    """download_normalized API 测试"""

    @patch("apps.contract_review.api.format_api.ReviewTask")
    def test_task_not_found(self, mock_model):
        from apps.contract_review.api.format_api import download_normalized

        mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_model.objects.get.side_effect = mock_model.DoesNotExist

        request = MagicMock()
        with pytest.raises(Exception):
            download_normalized(request, uuid.uuid4())


# ==================== Wiring ====================


class TestWiring:
    """services/wiring.py 测试"""

    def test_get_review_service(self):
        from apps.contract_review.services.wiring import get_review_service

        svc = get_review_service()
        assert svc is not None


# ==================== process_review ====================


class TestProcessReview:
    """process_review 异步任务测试"""

    def test_process_review_task_not_found(self):
        from apps.contract_review.services.review.review_service import process_review

        with patch("apps.contract_review.services.review.review_service.ReviewTaskRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_by_id.return_value = None
            mock_repo_cls.return_value = mock_repo
            # Should not raise
            process_review(str(uuid.uuid4()))

    def test_process_review_task_already_completed(self):
        from apps.contract_review.services.review.review_service import process_review

        with patch("apps.contract_review.services.review.review_service.ReviewTaskRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_task = MagicMock()
            mock_task.status = "completed"
            mock_repo.get_by_id.return_value = mock_task
            mock_repo_cls.return_value = mock_repo
            # Should not raise, just skip
            process_review(str(uuid.uuid4()))
