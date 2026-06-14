"""Long-tail coverage tests batch 3: scan service, log schemas, LLM backend."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# tests for apps.core.services.bound_folder_scan_service (30 missing)
# ---------------------------------------------------------------------------


class TestBoundFolderScanService:
    def _make_service(self, **kwargs):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        with patch("apps.core.services.bound_folder_scan_service.TextExtractionService"):
            with patch("apps.core.services.bound_folder_scan_service.MaterialClassificationService"):
                return BoundFolderScanService(**kwargs)

    def test_parse_version_v_pattern(self):
        svc = self._make_service()
        result = svc._parse_version("合同V2")
        assert result.base_name == "合同"
        assert result.version_token == "V2"
        assert result.version_rank == 102

    def test_parse_version_bracket_pattern(self):
        svc = self._make_service()
        result = svc._parse_version("合同(3)")
        assert result.base_name == "合同"
        assert result.version_token == "(3)"
        assert result.version_rank == 103

    def test_parse_version_chinese_bracket(self):
        svc = self._make_service()
        result = svc._parse_version("合同（5）")
        assert result.base_name == "合同"
        assert result.version_token == "(5)"
        assert result.version_rank == 105

    def test_parse_version_copy_pattern(self):
        svc = self._make_service()
        result = svc._parse_version("合同副本")
        assert result.base_name == "合同"
        assert result.version_token == "副本"
        assert result.version_rank == 0

    def test_parse_version_copy_pattern2(self):
        svc = self._make_service()
        result = svc._parse_version("合同复制")
        assert result.version_token == "复制"

    def test_parse_version_no_pattern(self):
        svc = self._make_service()
        result = svc._parse_version("普通文件")
        assert result.base_name == "普通文件"
        assert result.version_token == ""
        assert result.version_rank == 1

    def test_clean_base_name_normal(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService._clean_base_name("  hello  world  ") == "hello world"

    def test_clean_base_name_separators(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService._clean_base_name("a._-b") == "a b"

    def test_clean_base_name_empty_fallback(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService._clean_base_name("   ") == ""

    def test_normalize_group_key_normal(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService._normalize_group_key("Hello World") == "hello world"

    def test_normalize_group_key_empty(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService._normalize_group_key("") == "_"

    def test_calc_progress_normal(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService._calc_progress(idx=1, total=10) == 18
        assert BoundFolderScanService._calc_progress(idx=5, total=10) == 54

    def test_calc_progress_zero_total(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        assert BoundFolderScanService._calc_progress(idx=0, total=0) == 100

    def test_calc_progress_clamped(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        # idx=0, total=100 => (0/100)*90+9 = 9, but min is 10
        assert BoundFolderScanService._calc_progress(idx=0, total=100) == 10

    def test_notify_with_callback(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        cb = MagicMock()
        BoundFolderScanService._notify(cb, "status", 50, "file.pdf")
        cb.assert_called_once_with("status", 50, "file.pdf")

    def test_notify_without_callback(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        BoundFolderScanService._notify(None, "status", 50, "file.pdf")  # no-op

    def test_extract_parent_folder_hint_direct(self, tmp_path):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        file_path = tmp_path / "file.pdf"
        result = BoundFolderScanService._extract_parent_folder_hint(file_path, tmp_path)
        assert result == ""

    def test_extract_parent_folder_hint_subfolder(self, tmp_path):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        sub = tmp_path / "2-立案材料"
        sub.mkdir()
        file_path = sub / "test.pdf"
        result = BoundFolderScanService._extract_parent_folder_hint(file_path, tmp_path)
        assert result == "立案材料"

    def test_extract_parent_folder_hint_value_error(self, tmp_path):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        file_path = Path("/other/path/file.pdf")
        result = BoundFolderScanService._extract_parent_folder_hint(file_path, tmp_path)
        assert result == ""

    def test_collect_pdf_files(self, tmp_path):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.pdf").touch()
        (tmp_path / "c.txt").touch()
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "d.pdf").touch()

        files = BoundFolderScanService._collect_pdf_files(tmp_path)
        assert len(files) == 3
        assert all(f.suffix == ".pdf" for f in files)

    def test_deduplicate_files(self, tmp_path):
        svc = self._make_service()
        # Create files
        f1 = tmp_path / "合同V1.pdf"
        f2 = tmp_path / "合同V2.pdf"
        f3 = tmp_path / "其他.pdf"
        f1.touch()
        f2.touch()
        f3.touch()

        result = svc._deduplicate_files([f1, f2, f3])
        # 合同V1 and 合同V2 should be deduped to V2 (higher rank)
        assert len(result) == 2

    def test_build_candidate_unsupported_domain(self, tmp_path):
        svc = self._make_service()
        f = tmp_path / "test.pdf"
        f.touch()
        svc._classification_service.classify_contract_material.return_value = {}

        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="不支持"):
            svc._build_candidate(
                path=f, base_name="test", version_token="",
                extraction_method="none", text_excerpt="",
                domain="unsupported", enable_recognition=False,
                classification_context=None,
            )

    def test_build_candidate_contract_domain(self, tmp_path):
        svc = self._make_service()
        f = tmp_path / "test.pdf"
        f.touch()
        svc._classification_service.classify_contract_material.return_value = {
            "category": "archive_document", "confidence": 0.9, "reason": "test"
        }

        result = svc._build_candidate(
            path=f, base_name="test", version_token="",
            extraction_method="none", text_excerpt="",
            domain="contract", enable_recognition=False,
            classification_context=None,
        )
        assert result["suggested_category"] == "archive_document"

    def test_build_candidate_case_domain(self, tmp_path):
        svc = self._make_service()
        f = tmp_path / "test.pdf"
        f.touch()
        svc._classification_service.classify_case_material.return_value = {
            "category": "起诉状", "side": "plaintiff", "type_name_hint": "",
            "suggested_supervising_authority_id": None, "suggested_party_ids": [],
            "confidence": 0.8, "reason": "test",
        }

        result = svc._build_candidate(
            path=f, base_name="test", version_token="",
            extraction_method="none", text_excerpt="",
            domain="case", enable_recognition=False,
            classification_context=None,
        )
        assert result["suggested_category"] == "起诉状"
        assert result["suggested_side"] == "plaintiff"

    def test_scan_folder_not_accessible(self, tmp_path):
        svc = self._make_service()
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException, match="不可访问"):
            svc.scan_folder(folder_path="/nonexistent/path", domain="contract")

    def test_scan_folder_empty_dir(self, tmp_path):
        svc = self._make_service()
        svc._classification_service.classify_contract_material.return_value = {}

        result = svc.scan_folder(
            folder_path=str(tmp_path),
            domain="contract",
            enable_recognition=False,
        )
        assert result["summary"]["total_files"] == 0
        assert result["summary"]["deduped_files"] == 0

    def test_scan_folder_with_files(self, tmp_path):
        svc = self._make_service()
        svc._classification_service.classify_contract_material.return_value = {
            "category": "archive_document", "confidence": 0.5, "reason": ""
        }
        (tmp_path / "contract.pdf").touch()

        result = svc.scan_folder(
            folder_path=str(tmp_path),
            domain="contract",
            enable_recognition=False,
        )
        assert result["summary"]["total_files"] == 1
        assert result["summary"]["deduped_files"] == 1

    def test_extract_parent_folder_hint_cloud(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        scanned = MagicMock()
        scanned.as_posix = "/root/subfolder/file.pdf"

        result = BoundFolderScanService._extract_parent_folder_hint_cloud(scanned, "/root")
        assert result == "subfolder"

    def test_extract_parent_folder_hint_cloud_direct(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        scanned = MagicMock()
        scanned.as_posix = "/root/file.pdf"

        result = BoundFolderScanService._extract_parent_folder_hint_cloud(scanned, "/root")
        assert result == ""

    def test_extract_parent_folder_hint_cloud_value_error(self):
        from apps.core.services.bound_folder_scan_service import BoundFolderScanService

        scanned = MagicMock()
        scanned.as_posix = "/other/file.pdf"

        result = BoundFolderScanService._extract_parent_folder_hint_cloud(scanned, "/root")
        assert result == ""


# ---------------------------------------------------------------------------
# tests for apps.cases.schemas.log_schemas (48 missing)
# ---------------------------------------------------------------------------


class TestCaseLogSchemas:
    def test_validate_reminder_type_none(self):
        from apps.cases.schemas.log_schemas import _validate_reminder_type

        assert _validate_reminder_type(None) is None

    def test_validate_reminder_type_empty(self):
        from apps.cases.schemas.log_schemas import _validate_reminder_type

        with pytest.raises(ValueError, match="不能为空"):
            _validate_reminder_type("  ")

    def test_validate_reminder_type_invalid(self):
        from apps.cases.schemas.log_schemas import _validate_reminder_type

        with patch("apps.reminders.models.ReminderType") as mock_type:
            mock_type.values = ["meeting", "deadline"]
            with pytest.raises(ValueError, match="无效"):
                _validate_reminder_type("bad_type")

    def test_validate_reminder_type_valid(self):
        from apps.cases.schemas.log_schemas import _validate_reminder_type

        with patch("apps.reminders.models.ReminderType") as mock_type:
            mock_type.values = ["meeting", "deadline"]
            assert _validate_reminder_type("meeting") == "meeting"

    def test_case_log_in_both_reminder_fields(self):
        from apps.cases.schemas.log_schemas import CaseLogIn

        obj = CaseLogIn(case_id=1, content="test", reminder_type=None, reminder_time=None)
        assert obj.case_id == 1

    def test_case_log_actor_out_from_model(self):
        from apps.cases.schemas.log_schemas import CaseLogActorOut

        lawyer = SimpleNamespace(id=1, username="test", real_name="Test", phone="123")
        result = CaseLogActorOut.from_model(lawyer)
        assert result.id == 1
        assert result.real_name == "Test"

    def test_case_log_actor_out_from_model_no_real_name(self):
        from apps.cases.schemas.log_schemas import CaseLogActorOut

        lawyer = SimpleNamespace(id=2, username="u", real_name=None, phone=None)
        result = CaseLogActorOut.from_model(lawyer)
        assert result.real_name is None
        assert result.phone is None

    def test_case_log_actor_out_from_model_empty_real_name(self):
        from apps.cases.schemas.log_schemas import CaseLogActorOut

        lawyer = SimpleNamespace(id=3, username="u", real_name="", phone="")
        result = CaseLogActorOut.from_model(lawyer)
        assert result.real_name is None
        assert result.phone is None

    def test_case_log_out_resolve_primary_reminder_none(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        obj = SimpleNamespace(reminder_entries=[])
        result = CaseLogOut._resolve_primary_reminder(obj)
        assert result is None

    def test_case_log_out_resolve_primary_reminder_with_source(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        reminder = {"metadata": {"source": "case_log_api"}, "reminder_type": "meeting"}
        obj = SimpleNamespace(reminder_entries=[reminder])
        result = CaseLogOut._resolve_primary_reminder(obj)
        assert result == reminder

    def test_case_log_out_resolve_primary_reminder_fallback_last(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        r1 = {"metadata": {}, "reminder_type": "a"}
        r2 = {"metadata": {}, "reminder_type": "b"}
        obj = SimpleNamespace(reminder_entries=[r1, r2])
        result = CaseLogOut._resolve_primary_reminder(obj)
        assert result == r2

    def test_case_log_out_resolve_primary_reminder_no_metadata(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        r1 = {"reminder_type": "a"}
        obj = SimpleNamespace(reminder_entries=[r1])
        result = CaseLogOut._resolve_primary_reminder(obj)
        assert result == r1

    def test_case_log_out_resolve_reminder_type_none(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        obj = SimpleNamespace(reminder_entries=[])
        assert CaseLogOut.resolve_reminder_type(obj) is None

    def test_case_log_out_resolve_reminder_type_with_value(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        r = {"metadata": {"source": "case_log_api"}, "reminder_type": "meeting"}
        obj = SimpleNamespace(reminder_entries=[r])
        assert CaseLogOut.resolve_reminder_type(obj) == "meeting"

    def test_case_log_out_resolve_reminder_type_empty(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        r = {"metadata": {"source": "case_log_api"}, "reminder_type": ""}
        obj = SimpleNamespace(reminder_entries=[r])
        assert CaseLogOut.resolve_reminder_type(obj) is None

    def test_case_log_out_resolve_reminder_time_none(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        obj = SimpleNamespace(reminder_entries=[])
        assert CaseLogOut.resolve_reminder_time(obj) is None

    def test_case_log_out_resolve_actor_with_actor(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        actor = SimpleNamespace(id=1, username="u", real_name="R", phone="P")
        obj = SimpleNamespace(actor=actor, actor_id=1)
        result = CaseLogOut.resolve_actor_detail(obj)
        assert result.id == 1

    def test_case_log_out_resolve_actor_without_actor(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        obj = SimpleNamespace(actor=None, actor_id=42)
        result = CaseLogOut.resolve_actor_detail(obj)
        assert result.id == 42
        assert result.username == "lawyer_42"

    def test_case_log_out_resolve_actor_id(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        obj = SimpleNamespace(actor_id=5)
        assert CaseLogOut.resolve_actor(obj) == 5

    def test_case_log_attachment_out_resolvers(self):
        from apps.cases.schemas.log_schemas import CaseLogAttachmentOut

        obj = SimpleNamespace(file=None, uploaded_at=None)
        with patch("apps.cases.schemas.log_schemas.SchemaMixin._get_file_path", return_value="/path"):
            assert CaseLogAttachmentOut.resolve_file_path(obj) == "/path"
        with patch("apps.cases.schemas.log_schemas.SchemaMixin._get_file_url", return_value="/url"):
            assert CaseLogAttachmentOut.resolve_media_url(obj) == "/url"
        with patch("apps.cases.schemas.log_schemas.SchemaMixin._resolve_datetime", return_value=None):
            assert CaseLogAttachmentOut.resolve_uploaded_at(obj) is None

    def test_case_log_out_resolve_created_at(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        obj = SimpleNamespace(created_at=None)
        with patch("apps.cases.schemas.log_schemas.SchemaMixin._resolve_datetime", return_value=None):
            assert CaseLogOut.resolve_created_at(obj) is None

    def test_case_log_out_resolve_updated_at(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        obj = SimpleNamespace(updated_at=None)
        with patch("apps.cases.schemas.log_schemas.SchemaMixin._resolve_datetime", return_value=None):
            assert CaseLogOut.resolve_updated_at(obj) is None

    def test_case_log_out_resolve_reminders(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        entries = [{"type": "test"}]
        obj = SimpleNamespace(reminder_entries=entries)
        assert CaseLogOut.resolve_reminders(obj) == entries

    def test_case_log_out_resolve_attachments(self):
        from apps.cases.schemas.log_schemas import CaseLogOut

        mock_qs = MagicMock()
        mock_qs.all.return_value = [1, 2]
        obj = SimpleNamespace(attachments=MagicMock(all=mock_qs.all))
        result = CaseLogOut.resolve_attachments(obj)
        assert result == [1, 2]


# ---------------------------------------------------------------------------
# tests for apps.core.llm.backends.openai_compatible (35 missing)
# ---------------------------------------------------------------------------


class TestOpenAICompatibleBackend:
    def _make_backend(self, config=None):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend

        if config is None:
            config = MagicMock()
            config.api_key = "test-key"
            config.base_url = "http://test"
            config.default_model = "test-model"
            config.timeout = 30
            config.enabled = True
            config.embedding_model = ""
        return OpenAICompatibleBackend(config=config)

    def test_normalize_messages(self):
        b = self._make_backend()
        msgs = [{"role": "user", "content": "hi"}, {"role": "bad", "content": "x"}]
        result = b._normalize_messages(msgs)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "user"  # bad role => user

    def test_extract_usage_none(self):
        b = self._make_backend()
        usage = b._extract_usage(None)
        assert usage.prompt_tokens == 0

    def test_extract_usage_with_data(self):
        b = self._make_backend()
        mock_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        usage = b._extract_usage(mock_usage)
        assert usage.prompt_tokens == 10
        assert usage.total_tokens == 30

    def test_extract_content_empty_choices(self):
        b = self._make_backend()
        response = SimpleNamespace(choices=[])
        assert b._extract_content(response) == ""

    def test_extract_content_no_message(self):
        b = self._make_backend()
        choice = SimpleNamespace(message=None)
        response = SimpleNamespace(choices=[choice])
        assert b._extract_content(response) == ""

    def test_extract_content_normal(self):
        b = self._make_backend()
        msg = SimpleNamespace(content="hello", reasoning_content="")
        choice = SimpleNamespace(message=msg)
        response = SimpleNamespace(choices=[choice])
        assert b._extract_content(response) == "hello"

    def test_extract_content_reasoning_fallback(self):
        b = self._make_backend()
        msg = SimpleNamespace(content="", reasoning_content="reasoning output")
        choice = SimpleNamespace(message=msg)
        response = SimpleNamespace(choices=[choice])
        assert b._extract_content(response) == "reasoning output"

    def test_build_extra_body_kimi(self):
        b = self._make_backend()
        result = b._build_extra_body("kimi26-chat")
        assert result == {"chat_template_kwargs": {"thinking": False}}

    def test_build_extra_body_mimo(self):
        b = self._make_backend()
        result = b._build_extra_body("mimo-v1")
        assert result == {"chat_template_kwargs": {"thinking": False}}

    def test_build_extra_body_normal_model(self):
        b = self._make_backend()
        assert b._build_extra_body("gpt-4") is None

    def test_is_available_true(self):
        b = self._make_backend()
        assert b.is_available() is True

    def test_is_available_disabled(self):
        config = MagicMock()
        config.enabled = False
        b = self._make_backend(config=config)
        assert b.is_available() is False

    def test_is_available_no_api_key(self):
        config = MagicMock()
        config.enabled = True
        config.api_key = ""
        config.base_url = "http://test"
        config.default_model = "test-model"
        config.timeout = 30
        config.embedding_model = ""
        b = self._make_backend(config=config)
        # Override api_key to bypass LLMConfig database call
        b._api_key = ""
        assert b.is_available() is False

    def test_is_available_no_model(self):
        config = MagicMock()
        config.enabled = True
        config.api_key = "key"
        config.base_url = "http://test"
        config.default_model = ""
        config.timeout = 30
        config.embedding_model = ""
        b = self._make_backend(config=config)
        b._api_key = "key"
        b._default_model = ""
        assert b.is_available() is False

    def test_get_default_model(self):
        b = self._make_backend()
        assert b.get_default_model() == "test-model"

    def test_get_default_embedding_model(self):
        config = MagicMock()
        config.api_key = "k"
        config.base_url = "http://test"
        config.default_model = "default"
        config.timeout = 30
        config.embedding_model = "embed-v2"
        config.enabled = True
        b = self._make_backend(config=config)
        assert b.get_default_embedding_model() == "embed-v2"

    def test_resolve_embedding_model_explicit(self):
        b = self._make_backend()
        assert b._resolve_embedding_model("custom-model") == "custom-model"

    def test_resolve_embedding_model_fallback(self):
        config = MagicMock()
        config.api_key = "k"
        config.base_url = "http://test"
        config.default_model = "default"
        config.timeout = 30
        config.embedding_model = "embed-model"
        config.enabled = True
        b = self._make_backend(config=config)
        assert b._resolve_embedding_model() == "embed-model"

    def test_embed_texts_empty(self):
        b = self._make_backend()
        assert b.embed_texts([]) == []

    def test_raise_mapped_error_auth(self):
        import openai

        b = self._make_backend()
        from apps.core.llm.exceptions import LLMAuthenticationError

        err = openai.AuthenticationError(
            message="bad key",
            response=MagicMock(status_code=401),
            body=None,
        )
        with pytest.raises(LLMAuthenticationError):
            b._raise_mapped_error(err, 30, "http://test")

    def test_raise_mapped_error_timeout(self):
        import httpx

        b = self._make_backend()
        from apps.core.llm.exceptions import LLMTimeoutError

        err = httpx.TimeoutException("timeout")
        with pytest.raises(LLMTimeoutError):
            b._raise_mapped_error(err, 30, "http://test")

    def test_raise_mapped_error_connection(self):
        import httpx

        b = self._make_backend()
        from apps.core.llm.exceptions import LLMNetworkError

        err = httpx.ConnectError("conn refused")
        with pytest.raises(LLMNetworkError):
            b._raise_mapped_error(err, 30, "http://test")

    def test_raise_mapped_error_generic(self):
        b = self._make_backend()
        from apps.core.llm.exceptions import LLMAPIError

        err = RuntimeError("unknown error")
        with pytest.raises(LLMAPIError):
            b._raise_mapped_error(err, 30, "http://test")


# ---------------------------------------------------------------------------
# tests for apps.cases.services.data.cause_rule_service (49 missing)
# ---------------------------------------------------------------------------


class TestCauseRuleService:
    def _make_service(self):
        from apps.cases.services.data.cause_rule_service import CauseRuleService

        return CauseRuleService()

    def test_detect_special_case_type_empty(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=[]):
            with patch.object(svc, "get_ancestor_codes", return_value=[]):
                assert svc.detect_special_case_type(1) is None

    def test_detect_special_case_type_by_name(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=["申请支付令"]):
            with patch.object(svc, "get_ancestor_codes", return_value=[]):
                assert svc.detect_special_case_type(1) == "payment_order"

    def test_detect_special_case_type_by_code(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=["普通案由"]):
            with patch.object(svc, "get_ancestor_codes", return_value=["9001"]):
                assert svc.detect_special_case_type(1) == "personality_rights"

    def test_detect_special_case_type_ip_contract(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=[]):
            with patch.object(svc, "get_ancestor_codes", return_value=["9300"]):
                assert svc.detect_special_case_type(1) == "ip"

    def test_detect_special_case_type_ip_infringement(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=[]):
            with patch.object(svc, "get_ancestor_codes", return_value=["9363"]):
                assert svc.detect_special_case_type(1) == "ip"

    def test_detect_special_case_type_revoke_arbitration(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=["申请撤销仲裁裁决"]):
            with patch.object(svc, "get_ancestor_codes", return_value=[]):
                assert svc.detect_special_case_type(1) == "revoke_arbitration"

    def test_detect_special_case_type_public_notice(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=["公示催告程序案件"]):
            with patch.object(svc, "get_ancestor_codes", return_value=[]):
                assert svc.detect_special_case_type(1) == "public_notice"

    def test_detect_special_case_type_labor_dispute(self):
        svc = self._make_service()
        with patch.object(svc, "get_ancestor_names", return_value=["劳动争议"]):
            with patch.object(svc, "get_ancestor_codes", return_value=[]):
                assert svc.detect_special_case_type(1) == "labor_dispute"

    def test_get_fee_rule_normal(self):
        svc = self._make_service()
        with patch.object(svc, "detect_special_case_type", return_value=None):
            rule = svc.get_fee_rule(1)
            assert rule["use_property_rule"] is True
            assert rule["fixed_fee"] is None

    def test_get_fee_rule_revoke_arbitration(self):
        svc = self._make_service()
        with patch.object(svc, "detect_special_case_type", return_value="revoke_arbitration"):
            rule = svc.get_fee_rule(1)
            assert rule["fixed_fee"] == 400
            assert rule["use_property_rule"] is False
            assert "400元" in rule["fee_display_text"]

    def test_get_fee_rule_public_notice(self):
        svc = self._make_service()
        with patch.object(svc, "detect_special_case_type", return_value="public_notice"):
            rule = svc.get_fee_rule(1)
            assert rule["fixed_fee"] == 100
            assert "100元" in rule["fee_display_text"]

    def test_get_fee_rule_labor_dispute(self):
        svc = self._make_service()
        with patch.object(svc, "detect_special_case_type", return_value="labor_dispute"):
            rule = svc.get_fee_rule(1)
            assert rule["fixed_fee"] == 10
            assert "劳动争议" in rule["fee_display_text"]

    def test_get_fee_rule_personality_rights(self):
        svc = self._make_service()
        with patch.object(svc, "detect_special_case_type", return_value="personality_rights"):
            rule = svc.get_fee_rule(1)
            assert rule["fee_range"] is not None
            assert "100" in rule["fee_display_text"]

    def test_get_fee_rule_ip(self):
        svc = self._make_service()
        with patch.object(svc, "detect_special_case_type", return_value="ip"):
            rule = svc.get_fee_rule(1)
            assert rule["fee_range"] is not None
            assert "500" in rule["fee_display_text"]

    def test_get_fee_rule_payment_order(self):
        svc = self._make_service()
        with patch.object(svc, "detect_special_case_type", return_value="payment_order"):
            rule = svc.get_fee_rule(1)
            assert rule["use_property_rule"] is True
            assert rule["show_payment_order_fee"] is True
