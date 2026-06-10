"""Batch8 coverage tests for apps.workbench."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ── Workbench services ────────────────────────────────────────────────────


class TestWorkbenchServices:
    """Test workbench service imports."""

    def test_doc_extractor_import(self) -> None:
        from apps.workbench.services.doc_extractor import DocTextExtractor

        assert DocTextExtractor is not None

    def test_batch_service_import(self) -> None:
        from apps.workbench.services.batch_service import BatchAnalysisService

        assert BatchAnalysisService is not None

    def test_chat_service_import(self) -> None:
        from apps.workbench.services.chat_service import WorkbenchChatService

        assert WorkbenchChatService is not None


# ── Workbench models ──────────────────────────────────────────────────────


class TestWorkbenchModels:
    """Test workbench model imports."""

    def test_models_import(self) -> None:
        from apps.workbench import models

        assert models is not None


# ── Workbench APIs ────────────────────────────────────────────────────────


class TestWorkbenchAPIs:
    """Test workbench API imports."""

    def test_api_import(self) -> None:
        from apps.workbench.api import workbench_api

        assert workbench_api is not None
