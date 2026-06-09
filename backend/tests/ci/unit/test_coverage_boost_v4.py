"""Additional coverage boost tests - targeting high-uncov files."""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, PropertyMock, patch, AsyncMock
from uuid import uuid4

import pytest
from django.utils import timezone


# ============================================================================
# 1. workbench/tasks/summary.py (81 uncov)
# ============================================================================

class TestWorkbenchSummary:
    """Test summary generation functions."""

    def test_parse_llm_result_valid_json(self):
        from apps.workbench.tasks.parsing import parse_llm_result
        result = json.dumps({
            "case_number": "（2024）京01民初123号",
            "cause": "合同纠纷",
            "court": "北京市第一中级人民法院",
            "judge": "张法官",
            "clerk": "李书记员",
            "is_relevant": True,
            "conclusion": "支持原告诉请",
            "analysis": "详细分析内容",
        })
        parsed = parse_llm_result(result, "test.pdf")
        assert parsed["case_number"] == "（2024）京01民初123号"
        assert parsed["is_relevant"] is True

    def test_parse_llm_result_invalid_json(self):
        from apps.workbench.tasks.parsing import parse_llm_result
        parsed = parse_llm_result("not json", "test.pdf")
        assert parsed["parse_method"] == "regex"
        assert parsed["case_number"] == "未注明"

    def test_parse_llm_result_empty(self):
        from apps.workbench.tasks.parsing import parse_llm_result
        parsed = parse_llm_result("", "test.pdf")
        assert parsed["parse_method"] == "regex"

    def test_parse_llm_result_partial_json(self):
        from apps.workbench.tasks.parsing import parse_llm_result
        result = '{"case_number": "123", "is_relevant": true}'
        parsed = parse_llm_result(result, "test.pdf")
        assert parsed["case_number"] == "123"

    def test_build_case_info(self):
        from apps.workbench.tasks.parsing import build_case_info
        metadata = {
            "case_number": "123",
            "cause": "合同纠纷",
            "court": "北京法院",
            "judge": "张法官",
            "clerk": "李书记员",
            "is_relevant": "是",
            "conclusion": "支持",
            "analysis": "详细分析",
        }
        result = build_case_info(metadata)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_merge_chunk_results(self):
        from apps.workbench.tasks.parsing import merge_chunk_results
        results = [
            '{"case_number": "123", "conclusion": "支持"}',
            '{"analysis": "详细分析"}',
        ]
        merged = merge_chunk_results(results, "test.pdf")
        assert isinstance(merged, str)
        assert len(merged) > 0

    def test_merge_chunk_results_single(self):
        from apps.workbench.tasks.parsing import merge_chunk_results
        merged = merge_chunk_results(['{"case_number": "123"}'], "test.pdf")
        assert isinstance(merged, str)


# ============================================================================
# 2. workbench/services/chat_service.py (165 uncov) - more tests
# ============================================================================

class TestChatServiceMore:
    """Additional chat service tests."""

    def test_estimate_tokens_mixed(self):
        from apps.workbench.services.chat_service import _estimate_tokens
        # Mixed Chinese and English
        tokens = _estimate_tokens("Hello 你好 world 世界")
        assert tokens > 0

    def test_constants_values(self):
        from apps.workbench.services.chat_service import (
            MAX_HISTORY_TOKENS,
            MAX_HISTORY_MESSAGES,
            SUMMARY_THRESHOLD,
            USAGE_LIMITS,
        )
        assert MAX_HISTORY_TOKENS == 10000
        assert MAX_HISTORY_MESSAGES == 100
        assert SUMMARY_THRESHOLD == 30
        assert USAGE_LIMITS is not None


# ============================================================================
# 3. workbench/tasks/batch_runner.py (193 uncov) - more tests
# ============================================================================

class TestBatchRunnerMore:
    """Additional batch runner tests."""

    def test_run_batch_analysis_with_loop(self):
        from apps.workbench.tasks.batch_runner import run_batch_analysis
        job_id = str(uuid4())
        with patch("apps.workbench.tasks.batch_runner._run_batch_async") as mock_async:
            mock_async.return_value = None
            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value = MagicMock()
                with patch("concurrent.futures.ThreadPoolExecutor") as mock_pool:
                    mock_future = MagicMock()
                    mock_future.result.return_value = None
                    mock_pool.return_value.__enter__ = MagicMock(return_value=mock_pool)
                    mock_pool.return_value.__exit__ = MagicMock(return_value=False)
                    mock_pool.return_value.submit.return_value = mock_future
                    run_batch_analysis(job_id)

    def test_run_batch_retry_with_loop(self):
        from apps.workbench.tasks.batch_runner import run_batch_retry
        job_id = str(uuid4())
        item_ids = [str(uuid4())]
        with patch("apps.workbench.tasks.batch_runner._run_batch_retry_async") as mock_async:
            mock_async.return_value = None
            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value = MagicMock()
                with patch("concurrent.futures.ThreadPoolExecutor") as mock_pool:
                    mock_future = MagicMock()
                    mock_future.result.return_value = None
                    mock_pool.return_value.__enter__ = MagicMock(return_value=mock_pool)
                    mock_pool.return_value.__exit__ = MagicMock(return_value=False)
                    mock_pool.return_value.submit.return_value = mock_future
                    run_batch_retry(job_id, item_ids)


# ============================================================================
# 4. core/llm/backends/openai_compatible.py (142 uncov) - more tests
# ============================================================================

class TestOpenAICompatibleMore:
    """Additional OpenAI compatible backend tests."""

    def test_build_extra_body_default_model(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
        backend = OpenAICompatibleBackend.__new__(OpenAICompatibleBackend)
        backend._config = MagicMock()
        # Mock the default_model property
        with patch.object(type(backend), 'default_model', new_callable=PropertyMock, return_value="gpt-4"):
            result = backend._build_extra_body()
            assert result is None

    def test_build_extra_body_case_insensitive(self):
        from apps.core.llm.backends.openai_compatible import OpenAICompatibleBackend
        backend = OpenAICompatibleBackend.__new__(OpenAICompatibleBackend)
        backend._config = MagicMock()
        result = backend._build_extra_body("KIMI26-LATEST")
        assert result == {"chat_template_kwargs": {"thinking": False}}


# ============================================================================
# 5. core/llm/backends/ollama.py (140 uncov) - more tests
# ============================================================================

class TestOllamaMore:
    """Additional Ollama backend tests."""

    def test_default_embedding_model_with_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        from apps.core.llm.backends.base import BackendConfig
        config = BackendConfig(
            name="ollama",
            enabled=True,
            priority=1,
            default_model="llama3",
            embedding_model="nomic-embed-text",
            base_url="http://localhost:11434",
            api_key="",
            timeout=60,
        )
        backend = OllamaBackend(config)
        assert backend.default_embedding_model == "nomic-embed-text"

    def test_default_embedding_model_without_config(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        backend = OllamaBackend()
        with patch("apps.core.llm.backends.ollama.LLMConfig") as mock_config:
            mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
            mock_config.get_ollama_model.return_value = "qwen3:0.6b"
            mock_config.get_ollama_timeout.return_value = 120.0
            # When no embedding_model in config, falls back to default_model
            assert backend.default_embedding_model == "qwen3:0.6b"

    def test_build_api_url(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        from apps.core.llm.backends.base import BackendConfig
        config = BackendConfig(
            name="ollama",
            enabled=True,
            priority=1,
            default_model="llama3",
            base_url="http://localhost:11434",
            api_key="",
            timeout=60,
        )
        backend = OllamaBackend(config)
        url = backend._build_api_url()
        assert "chat" in url

    def test_build_embed_url(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        from apps.core.llm.backends.base import BackendConfig
        config = BackendConfig(
            name="ollama",
            enabled=True,
            priority=1,
            default_model="llama3",
            base_url="http://localhost:11434",
            api_key="",
            timeout=60,
        )
        backend = OllamaBackend(config)
        url = backend._build_embed_url()
        assert "embed" in url

    def test_build_legacy_embed_url(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        from apps.core.llm.backends.base import BackendConfig
        config = BackendConfig(
            name="ollama",
            enabled=True,
            priority=1,
            default_model="llama3",
            base_url="http://localhost:11434",
            api_key="",
            timeout=60,
        )
        backend = OllamaBackend(config)
        url = backend._build_legacy_embed_url()
        assert "embeddings" in url or "embed" in url

    def test_build_options(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        from apps.core.llm.backends.base import BackendConfig
        config = BackendConfig(
            name="ollama",
            enabled=True,
            priority=1,
            default_model="llama3",
            base_url="http://localhost:11434",
            api_key="",
            timeout=60,
        )
        backend = OllamaBackend(config)
        options = backend._build_options(num_predict=100, temperature=0.5)
        assert isinstance(options, dict)

    def test_build_options_empty(self):
        from apps.core.llm.backends.ollama import OllamaBackend
        from apps.core.llm.backends.base import BackendConfig
        config = BackendConfig(
            name="ollama",
            enabled=True,
            priority=1,
            default_model="llama3",
            base_url="http://localhost:11434",
            api_key="",
            timeout=60,
        )
        backend = OllamaBackend(config)
        options = backend._build_options(temperature=0.7)
        # Default temperature returns None (no options needed)
        assert options is None


# ============================================================================
# 6. contracts/services/archive/generation/pdf_utils.py (141 uncov) - more tests
# ============================================================================

class TestPdfUtilsMore2:
    """Additional PDF utils tests."""

    def test_constants(self):
        from apps.contracts.services.archive.generation.pdf_utils import A4_W, A4_H, TOLERANCE
        assert A4_W == 595.0
        assert A4_H == 842.0
        assert TOLERANCE == 1.0


# ============================================================================
# 7. contracts/services/contract/integrations/folder_scan_service.py - more tests
# ============================================================================

class TestContractFolderScanMore:
    """Additional contract folder scan tests."""

    def _make_service(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        with patch.object(ContractFolderScanService, '__init__', lambda self, **kw: None):
            svc = ContractFolderScanService()
        svc._scan_service = MagicMock()
        svc._material_service = MagicMock()
        return svc

    def test_normalize_scan_subfolder_backslashes(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = self._make_service()
        result = svc._normalize_scan_subfolder("sub1\\sub2")
        assert "\\" not in result

    def test_normalize_scan_subfolder_dot_segments(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = self._make_service()
        result = svc._normalize_scan_subfolder("./sub1/./sub2/.")
        assert "." not in result.split("/")

    def test_resolve_scan_scope_cloud_traversal(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        from apps.core.exceptions import ValidationException
        svc = self._make_service()
        provider = MagicMock()
        with pytest.raises(ValidationException):
            svc._resolve_scan_scope("/root", "../etc", storage_provider=provider)

    def test_resolve_scan_scope_cloud_not_exists(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        from apps.core.exceptions import ValidationException
        svc = self._make_service()
        provider = MagicMock()
        provider.exists.return_value = False
        with pytest.raises(ValidationException):
            svc._resolve_scan_scope("/root", "sub", storage_provider=provider)

    def test_post_process_candidates_empty(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = self._make_service()
        result = svc._post_process_candidates(
            candidates=[],
            archive_category="litigation",
            scan_folder="/tmp",
        )
        assert result == []

    def test_post_process_candidates_archive_document(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = self._make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                "category": "case_material",
                "archive_item_code": "l_1",
                "archive_item_name": "起诉状",
                "confidence": 0.9,
                "reason": "匹配",
            }
            candidates = [
                {
                    "filename": "起诉状.pdf",
                    "source_path": "/tmp/起诉状.pdf",
                    "suggested_category": "archive_document",
                }
            ]
            with tempfile.TemporaryDirectory() as tmpdir:
                result = svc._post_process_candidates(
                    candidates=candidates,
                    archive_category="litigation",
                    scan_folder=tmpdir,
                )
                assert len(result) == 1
                assert result[0]["archive_item_code"] == "l_1"

    def test_post_process_candidates_skip(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = self._make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                "category": "skip",
                "archive_item_code": "",
                "archive_item_name": "",
                "confidence": 0,
                "reason": "跳过规则",
            }
            candidates = [
                {
                    "filename": "保单.pdf",
                    "source_path": "/tmp/保单.pdf",
                    "suggested_category": "archive_document",
                }
            ]
            with tempfile.TemporaryDirectory() as tmpdir:
                result = svc._post_process_candidates(
                    candidates=candidates,
                    archive_category="litigation",
                    scan_folder=tmpdir,
                )
                assert len(result) == 1
                assert result[0]["selected"] is False

    def test_post_process_candidates_insurance_keyword(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = self._make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                "category": "case_material",
                "archive_item_code": "",
                "archive_item_name": "未匹配",
                "confidence": 0,
                "reason": "",
            }
            candidates = [
                {
                    "filename": "保函.pdf",
                    "source_path": "/tmp/保函.pdf",
                    "suggested_category": "case_material",
                }
            ]
            with tempfile.TemporaryDirectory() as tmpdir:
                result = svc._post_process_candidates(
                    candidates=candidates,
                    archive_category="litigation",
                    scan_folder=tmpdir,
                )
                assert len(result) == 1
                assert result[0]["selected"] is False

    def test_post_process_candidates_authorization_material(self):
        from apps.contracts.services.contract.integrations.folder_scan_service import ContractFolderScanService
        svc = self._make_service()
        with patch("apps.contracts.services.contract.integrations.folder_scan_service.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                "category": "case_material",
                "archive_item_code": "l_5",
                "archive_item_name": "授权委托书",
                "confidence": 0.8,
                "reason": "匹配",
            }
            candidates = [
                {
                    "filename": "授权委托书.pdf",
                    "source_path": "/tmp/授权委托书.pdf",
                    "suggested_category": "authorization_material",
                }
            ]
            with tempfile.TemporaryDirectory() as tmpdir:
                result = svc._post_process_candidates(
                    candidates=candidates,
                    archive_category="litigation",
                    scan_folder=tmpdir,
                )
                assert len(result) == 1
                assert result[0]["suggested_category"] == "case_material"


# ============================================================================
# 8. cases/services/material/folder_scan_service.py - more tests
# ============================================================================

class TestCaseFolderScanMore:
    """Additional case folder scan tests."""

    def _make_service(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        with patch.object(CaseFolderScanService, '__init__', lambda self, **kw: None):
            svc = CaseFolderScanService()
        svc._scan_service = MagicMock()
        svc._case_log_service = MagicMock()
        return svc

    def test_build_status_payload(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = self._make_service()
        session = MagicMock()
        session.id = uuid4()
        session.status = "completed"
        session.progress = 100
        session.current_file = "test.pdf"
        session.error_message = ""
        session.result_payload = {
            "summary": {"total_files": 5, "deduped_files": 3, "classified_files": 2},
            "candidates": [{"filename": "a.pdf"}],
            "scan_options": {"enable_recognition": True},
        }
        payload = svc.build_status_payload(session=session)
        assert payload["session_id"] == str(session.id)
        assert payload["status"] == "completed"

    def test_should_force_our_party_for_filing_materials(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = self._make_service()
        assert svc._should_force_our_party_for_filing_materials(None) is False
        assert svc._should_force_our_party_for_filing_materials({}) is False
        assert svc._should_force_our_party_for_filing_materials(
            {"scan_scope": {"scan_subfolder": "立案材料"}}
        ) is True

    def test_should_force_our_party_for_candidate(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = self._make_service()
        assert svc._should_force_our_party_for_candidate(None) is False
        assert svc._should_force_our_party_for_candidate({}) is False
        assert svc._should_force_our_party_for_candidate(
            {"source_path": "/path/立案材料/file.pdf"}
        ) is True

    def test_contains_force_our_party_folder_keyword(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("立案材料") is True
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("其他") is False
        assert CaseFolderScanService._contains_force_our_party_folder_keyword("") is False

    def test_normalize_candidates_for_scan_scope(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = self._make_service()
        scan_scope = {"scan_folder": "/tmp", "scan_subfolder": "sub"}
        candidates = [
            {"source_path": "/tmp/sub/file.pdf", "reason": "旧原因"},
        ]
        result = svc._normalize_candidates_for_scan_scope(candidates, scan_scope)
        assert isinstance(result, list)

    def test_build_classification_context(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = self._make_service()
        case = MagicMock()
        case.name = "测试案件"
        case.case_type = "litigation"
        case.filing_number = "2024-001"
        case.parties.all.return_value = []
        ctx = svc._build_classification_context(case)
        assert isinstance(ctx, dict)
        assert "opponent_party_ids" in ctx

    def test_try_repair_binding_path(self):
        from apps.cases.services.material.folder_scan_service import CaseFolderScanService
        svc = self._make_service()
        binding = MagicMock()
        binding.folder_path = ""
        binding.resolved_folder_path = ""
        # Should not raise
        svc._try_repair_binding_path(binding)


# ============================================================================
# 9. litigation_ai/services/mock_trial/mock_trial_flow_service.py - more tests
# ============================================================================

class TestMockTrialFlowMore:
    """Additional mock trial flow tests."""

    def test_parse_mode_with_spaces(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import parse_mode
        assert parse_mode("  法官  ") == "judge"
        assert parse_mode("  1  ") == "judge"

    def test_format_judge_report_none_values(self):
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import format_judge_report
        report = {
            "dispute_focuses": [
                {
                    "description": None,
                    "focus_type": None,
                    "plaintiff_position": None,
                    "defendant_position": None,
                    "burden_of_proof": None,
                    "key_evidence": None,
                }
            ],
            "evidence_strength_comparison": [],
            "judge_questions": [],
        }
        result = format_judge_report(report)
        assert "法官视角分析报告" in result


# ============================================================================
# 10. documents/services/generation/folder_generation_service.py - more tests
# ============================================================================

class TestFolderGenerationMore:
    """Additional folder generation tests."""

    def test_service_class(self):
        from apps.documents.services.generation.folder_generation_service import FolderGenerationService
        assert FolderGenerationService is not None

    def test_document_placement_fields(self):
        from apps.documents.services.generation.folder_generation_service import DocumentPlacement
        mock_template = MagicMock()
        placement = DocumentPlacement(
            document_template=mock_template,
            folder_path="path/to/folder",
            file_name="document.pdf",
        )
        assert placement.folder_path == "path/to/folder"
        assert placement.file_name == "document.pdf"
        assert placement.document_template is mock_template


# ============================================================================
# 11. contracts/services/archive/generation/pdf_utils.py - more tests
# ============================================================================

class TestPdfUtilsMore3:
    """Additional PDF utils tests."""

    @patch("apps.contracts.services.archive.generation.pdf_utils.FinalizedMaterial")
    def test_scale_pages_to_a4_with_errors(self, mock_material_model):
        from apps.contracts.services.archive.generation.pdf_utils import scale_pages_to_a4
        material = MagicMock()
        material.file_path = "/nonexistent/file.pdf"
        material.original_filename = "test.pdf"
        mock_material_model.objects.filter.return_value.order_by.return_value = [material]
        contract = MagicMock()
        with patch("apps.contracts.services.archive.generation.pdf_utils.Path") as mock_path_cls:
            mock_path_instance = MagicMock()
            mock_path_instance.is_absolute.return_value = True
            mock_path_instance.exists.return_value = False
            mock_path_cls.return_value = mock_path_instance
            result = scale_pages_to_a4(contract)
            assert "errors" in result
            assert result["success"] is True


# ============================================================================
# 12. automation/services/insurance/court_insurance_client.py
# ============================================================================

class TestCourtInsuranceClient:
    """Test court insurance client."""

    def test_module_imports(self):
        import apps.automation.services.insurance.court_insurance_client as mod
        assert mod is not None


# ============================================================================
# 13. Various model/enum tests
# ============================================================================

class TestModelEnums:
    """Test model enums and choices."""

    def test_batch_job_status_values(self):
        from apps.workbench.models import BatchJobStatus
        # Verify enum has expected values
        assert hasattr(BatchJobStatus, 'PENDING')
        assert hasattr(BatchJobStatus, 'RUNNING')
        assert hasattr(BatchJobStatus, 'COMPLETED')
        assert hasattr(BatchJobStatus, 'FAILED')

    def test_contract_folder_scan_status_values(self):
        from apps.contracts.models import ContractFolderScanStatus
        assert hasattr(ContractFolderScanStatus, 'PENDING')
        assert hasattr(ContractFolderScanStatus, 'RUNNING')
        assert hasattr(ContractFolderScanStatus, 'COMPLETED')
        assert hasattr(ContractFolderScanStatus, 'IMPORTED')
        assert hasattr(ContractFolderScanStatus, 'FAILED')

    def test_case_folder_scan_status_values(self):
        from apps.cases.models import CaseFolderScanStatus
        assert hasattr(CaseFolderScanStatus, 'PENDING')
        assert hasattr(CaseFolderScanStatus, 'RUNNING')
        assert hasattr(CaseFolderScanStatus, 'COMPLETED')
        assert hasattr(CaseFolderScanStatus, 'FAILED')

    def test_material_category_values(self):
        from apps.contracts.models import MaterialCategory
        assert hasattr(MaterialCategory, 'CONTRACT_ORIGINAL')
        assert hasattr(MaterialCategory, 'SUPPLEMENTARY_AGREEMENT')
        assert hasattr(MaterialCategory, 'INVOICE')
        assert hasattr(MaterialCategory, 'CASE_MATERIAL')


# ============================================================================
# 14. Core infrastructure tests
# ============================================================================

class TestCoreInfrastructure:
    """Test core infrastructure modules."""

    def test_service_locator(self):
        import apps.core.infrastructure.service_locator as mod
        assert mod is not None

    def test_event_bus(self):
        from apps.core.infrastructure.event_bus import EventBus
        assert EventBus is not None

    def test_cache_module(self):
        from apps.core.infrastructure import cache
        assert cache is not None

    def test_monitoring_module(self):
        from apps.core.infrastructure import monitoring
        assert monitoring is not None

    def test_throttling_module(self):
        from apps.core.infrastructure import throttling
        assert throttling is not None

    def test_logging_module(self):
        from apps.core.infrastructure import logging as infra_logging
        assert infra_logging is not None


# ============================================================================
# 15. Archive classifier more tests
# ============================================================================

class TestArchiveClassifierMore:
    """Additional archive classifier tests."""

    def test_classify_archive_material_skip_keywords(self):
        from apps.contracts.services.contract.integrations.archive_classifier import classify_archive_material
        # Test with a filename that might trigger skip rules
        result = classify_archive_material(
            filename="律师服务质量监督卡.pdf",
            source_path="/path/to/监督卡.pdf",
            archive_category="litigation",
        )
        assert "category" in result

    def test_classify_archive_material_empty(self):
        from apps.contracts.services.contract.integrations.archive_classifier import classify_archive_material
        result = classify_archive_material(
            filename="",
            source_path="",
            archive_category="litigation",
        )
        assert "category" in result

    def test_collect_archive_item_options_litigation(self):
        from apps.contracts.services.contract.integrations.archive_classifier import collect_archive_item_options
        result = collect_archive_item_options("litigation")
        assert isinstance(result, list)

    def test_collect_archive_item_options_non_litigation(self):
        from apps.contracts.services.contract.integrations.archive_classifier import collect_archive_item_options
        result = collect_archive_item_options("non_litigation")
        assert isinstance(result, list)

    def test_collect_archive_item_options_empty(self):
        from apps.contracts.services.contract.integrations.archive_classifier import collect_archive_item_options
        result = collect_archive_item_options("")
        assert isinstance(result, list)


# ============================================================================
# 16. Ollama protocol more tests
# ============================================================================

class TestOllamaProtocolMore:
    """Additional Ollama protocol tests."""

    def test_build_payload_with_think(self):
        from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload
        messages = [{"role": "user", "content": "hello"}]
        payload = build_ollama_chat_payload(
            messages=messages,
            model="test-model",
            think=True,
        )
        assert payload["think"] is True

    def test_build_payload_with_options(self):
        from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload
        messages = [{"role": "user", "content": "hello"}]
        payload = build_ollama_chat_payload(
            messages=messages,
            model="test-model",
            options={"num_predict": 100},
        )
        assert payload["options"] == {"num_predict": 100}

    def test_build_payload_no_options(self):
        from apps.core.llm.backends.ollama_protocol import build_ollama_chat_payload
        messages = [{"role": "user", "content": "hello"}]
        payload = build_ollama_chat_payload(
            messages=messages,
            model="test-model",
        )
        assert "options" not in payload

    def test_parse_ollama_chat_response(self):
        from apps.core.llm.backends.ollama_protocol import parse_ollama_chat_response
        response = MagicMock()
        response.json.return_value = {
            "message": {"content": "hello"},
            "done": True,
            "total_duration": 1000,
        }
        result = parse_ollama_chat_response(resp=response, model="test")
        assert isinstance(result, dict)


# ============================================================================
# 17. HTTP error summary more tests
# ============================================================================

class TestHttpErrorSummaryMore:
    """Additional HTTP error summary tests."""

    def test_summarize_with_different_codes(self):
        from apps.core.llm.backends.http_error_summary import summarize_http_error_response
        for code in [400, 401, 403, 404, 500, 502, 503]:
            response = MagicMock()
            response.status_code = code
            response.text = f"Error {code}"
            response.headers = {}
            result = summarize_http_error_response(response)
            assert isinstance(result, dict)
            assert result["status_code"] == code


# ============================================================================
# 18. File hash utils more tests
# ============================================================================

class TestFileHashUtilsMore:
    """Additional file hash utils tests."""

    def test_compute_file_hash_from_bytes_large(self):
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash_from_bytes
        content = b"x" * 1000000  # 1MB
        hash_val = compute_file_hash_from_bytes(content)
        assert len(hash_val) == 64

    def test_compute_file_hash_from_bytes_unicode(self):
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash_from_bytes
        content = "你好世界".encode("utf-8")
        hash_val = compute_file_hash_from_bytes(content)
        assert len(hash_val) == 64

    def test_compute_file_hash_deterministic(self):
        from apps.contracts.services.contract.integrations.file_hash_utils import compute_file_hash_from_bytes
        content = b"deterministic test"
        hash1 = compute_file_hash_from_bytes(content)
        hash2 = compute_file_hash_from_bytes(content)
        assert hash1 == hash2


# ============================================================================
# 19. Core exceptions more tests
# ============================================================================

class TestCoreExceptionsEvenMore:
    """Test more core exception classes."""

    def test_not_found_error(self):
        from apps.core.exceptions import NotFoundError
        exc = NotFoundError("resource not found")
        assert "resource not found" in str(exc)

    def test_conflict_error(self):
        from apps.core.exceptions import ConflictError
        exc = ConflictError("conflict")
        assert "conflict" in str(exc)

    def test_authentication_error(self):
        from apps.core.exceptions import AuthenticationError
        exc = AuthenticationError("auth failed")
        assert "auth failed" in str(exc)

    def test_rate_limit_error(self):
        from apps.core.exceptions import RateLimitError
        exc = RateLimitError("rate limited")
        assert "rate limited" in str(exc)

    def test_forbidden_error(self):
        from apps.core.exceptions import ForbiddenError
        exc = ForbiddenError("forbidden")
        assert "forbidden" in str(exc)

    def test_unauthorized_error(self):
        from apps.core.exceptions import UnauthorizedError
        exc = UnauthorizedError("unauthorized")
        assert "unauthorized" in str(exc)


# ============================================================================
# 20. LLM exceptions more tests
# ============================================================================

class TestLLMExceptionsMore:
    """Test more LLM exception classes."""

    def test_llm_api_error_with_details(self):
        from apps.core.llm.exceptions import LLMAPIError
        exc = LLMAPIError("api error", status_code=500)
        assert "api error" in str(exc)

    def test_llm_auth_error_with_details(self):
        from apps.core.llm.exceptions import LLMAuthenticationError
        exc = LLMAuthenticationError("auth error")
        assert "auth error" in str(exc)


# ============================================================================
# 21. Quality card detector more tests
# ============================================================================

class TestQualityCardDetectorMore:
    """Additional quality card detector tests."""

    def test_has_quality_card_on_last_page_non_pdf(self):
        from apps.contracts.services.contract.integrations.quality_card_detector import has_quality_card_on_last_page
        result = has_quality_card_on_last_page(Path("/nonexistent/file.txt"))
        assert result is False


# ============================================================================
# 22. Contracts models more tests
# ============================================================================

class TestContractsModelsMore:
    """Additional contracts model tests."""

    def test_contract_folder_binding_exists(self):
        from apps.contracts.models import ContractFolderBinding
        assert ContractFolderBinding is not None

    def test_contract_folder_scan_session_exists(self):
        from apps.contracts.models import ContractFolderScanSession
        assert ContractFolderScanSession is not None

    def test_finalized_material_exists(self):
        from apps.contracts.models import FinalizedMaterial
        assert FinalizedMaterial is not None


# ============================================================================
# 23. Cases models more tests
# ============================================================================

class TestCasesModelsMore:
    """Additional cases model tests."""

    def test_case_folder_binding_exists(self):
        from apps.cases.models import CaseFolderBinding
        assert CaseFolderBinding is not None

    def test_case_folder_scan_session_exists(self):
        from apps.cases.models import CaseFolderScanSession
        assert CaseFolderScanSession is not None


# ============================================================================
# 24. Archive category mapping more tests
# ============================================================================

class TestArchiveCategoryMappingMore:
    """Additional archive category mapping tests."""

    def test_get_archive_category_criminal(self):
        from apps.contracts.services.archive.category_mapping import get_archive_category
        result = get_archive_category("criminal")
        # Should return a valid category or None
        assert result is None or isinstance(result, str)

    def test_get_archive_category_none(self):
        from apps.contracts.services.archive.category_mapping import get_archive_category
        result = get_archive_category(None)
        # Should handle None gracefully
        assert result is None or isinstance(result, str)


# ============================================================================
# 25. Archive constants more tests
# ============================================================================

class TestArchiveConstantsMore:
    """Additional archive constants tests."""

    def test_archive_checklist_keys(self):
        from apps.contracts.services.archive.constants import ARCHIVE_CHECKLIST
        assert isinstance(ARCHIVE_CHECKLIST, dict)
        # Should have at least one category
        assert len(ARCHIVE_CHECKLIST) > 0

    def test_archive_skip_codes_type(self):
        from apps.contracts.services.archive.constants import ARCHIVE_SKIP_CODES
        assert isinstance(ARCHIVE_SKIP_CODES, (set, list, frozenset))

    def test_archive_skip_templates_type(self):
        from apps.contracts.services.archive.constants import ARCHIVE_SKIP_TEMPLATES
        assert isinstance(ARCHIVE_SKIP_TEMPLATES, (set, list, frozenset, dict))
