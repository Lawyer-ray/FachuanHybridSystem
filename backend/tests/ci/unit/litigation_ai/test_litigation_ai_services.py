"""
Tests for apps.litigation_ai.services — 诉讼AI服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ============================================================
# MockTrial Flow Service 测试
# ============================================================


class TestMockTrialFlowService:
    """MockTrialFlowService 测试"""

    def test_service_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService

        assert MockTrialFlowService is not None

    def test_judge_perspective_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial.judge_perspective_service import JudgePerspectiveService

        assert JudgePerspectiveService is not None

    def test_report_service_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial.report_service import MockTrialReportService

        assert MockTrialReportService is not None

    def test_export_service_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial.export_service import MockTrialExportService

        assert MockTrialExportService is not None


# ============================================================
# Evidence Services 测试
# ============================================================


class TestLitigationEvidenceServices:
    """诉讼AI证据服务测试"""

    def test_evidence_rag_importable(self) -> None:
        from apps.litigation_ai.services.evidence import evidence_rag_service

        assert evidence_rag_service is not None

    def test_evidence_text_extraction_importable(self) -> None:
        from apps.litigation_ai.services.evidence import evidence_text_extraction_service

        assert evidence_text_extraction_service is not None

    def test_evidence_digest_importable(self) -> None:
        from apps.litigation_ai.services.evidence import evidence_digest_service

        assert evidence_digest_service is not None


# ============================================================
# Generation Services 测试
# ============================================================


class TestLitigationGenerationServices:
    """诉讼AI生成服务测试"""

    def test_placeholder_render_importable(self) -> None:
        from apps.litigation_ai.services.generation import placeholder_render_service

        assert placeholder_render_service is not None

    def test_litigation_agent_importable(self) -> None:
        from apps.litigation_ai.services.generation import litigation_agent_service

        assert litigation_agent_service is not None


# ============================================================
# Wiring 测试
# ============================================================


class TestLitigationWiring:
    """诉讼AI服务装配测试"""

    def test_wiring_importable(self) -> None:
        from apps.litigation_ai.services import wiring

        assert wiring is not None
