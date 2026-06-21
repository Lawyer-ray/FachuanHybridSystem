"""Tests for more pure-logic modules: property_clue_service helpers, contract helpers, etc."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)


from apps.core.exceptions import ValidationException


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_basic(self):
        from apps.core.llm.backends.base import LLMResponse

        r = LLMResponse(
            content="hello",
            model="qwen3",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            duration_ms=100.0,
            backend="ollama",
        )
        assert r.content == "hello"
        assert r.total_tokens == 15
        assert r.backend == "ollama"


# ---------------------------------------------------------------------------
# LLMStreamChunk and LLMUsage
# ---------------------------------------------------------------------------


class TestLLMStreamChunk:
    def test_basic(self):
        from apps.core.llm.backends.base import LLMStreamChunk, LLMUsage

        usage = LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        chunk = LLMStreamChunk(content="hello", usage=usage, model="qwen3", backend="ollama")
        assert chunk.content == "hello"
        assert chunk.usage.total_tokens == 15

    def test_defaults(self):
        from apps.core.llm.backends.base import LLMStreamChunk

        chunk = LLMStreamChunk()
        assert chunk.content == ""
        assert chunk.usage is None


# ---------------------------------------------------------------------------
# BackendConfig dataclass
# ---------------------------------------------------------------------------


class TestBackendConfig:
    def test_basic(self):
        from apps.core.llm.backends.base import BackendConfig

        cfg = BackendConfig(
            name="ollama",
            enabled=True,
            priority=2,
            default_model="qwen3:0.6b",
            base_url="http://localhost:11434",
            timeout=300,
        )
        assert cfg.name == "ollama"
        assert cfg.enabled is True
        assert cfg.api_key is None
        assert cfg.extra_options == {}


# ---------------------------------------------------------------------------
# DocumentDeliveryRecord.to_dict edge cases
# ---------------------------------------------------------------------------


class TestDocumentDeliveryRecordExtended:
    def test_full_record(self):
        from apps.automation.services.document_delivery.data_classes import DocumentDeliveryRecord

        record = DocumentDeliveryRecord(
            case_number="2025-粤01民初1号",
            send_time=datetime(2025, 1, 15, 10, 0, 0),
            element_index=3,
            document_name="判决书",
            court_name="广州市法院",
            delivery_event_id="evt_456",
        )
        d = record.to_dict()
        assert d["element_index"] == 3
        assert d["document_name"] == "判决书"
        assert d["court_name"] == "广州市法院"
        assert d["delivery_event_id"] == "evt_456"


# ---------------------------------------------------------------------------
# CaseNumberExtractorService lazy loading
# ---------------------------------------------------------------------------


class TestCaseNumberExtractorService:
    def test_init(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService

        svc = CaseNumberExtractorService()
        assert svc._document_processing_service is None
        assert svc._case_service is None

    def test_init_with_injection(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService

        mock_doc = MagicMock()
        mock_case = MagicMock()
        svc = CaseNumberExtractorService(
            document_processing_service=mock_doc,
            case_service=mock_case,
        )
        assert svc.document_processing_service is mock_doc
        assert svc.case_service is mock_case

    def test_extract_empty_path(self):
        from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService

        svc = CaseNumberExtractorService()
        result = svc.extract_from_document("")
        assert result == []


# ---------------------------------------------------------------------------
# InsuranceClientFacade
# ---------------------------------------------------------------------------


class TestInsuranceClientFacade:
    def test_init(self):
        from plugins.court_automation.preservation_quote.preservation_quote.client_facade import InsuranceClientFacade

        mock_client = MagicMock()
        facade = InsuranceClientFacade(client=mock_client)
        assert facade.client is mock_client
