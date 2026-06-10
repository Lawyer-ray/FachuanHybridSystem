"""Batch7 coverage tests for apps.pdf_splitting."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestPdfSplittingModuleImports:
    """Test that pdf_splitting module components are importable."""

    def test_import_pdf_splitting_admin(self) -> None:
        from apps.pdf_splitting.admin import pdf_splitting_admin
        assert pdf_splitting_admin is not None

    def test_import_pdf_splitting_api(self) -> None:
        from apps.pdf_splitting.api import pdf_splitting_api
        assert pdf_splitting_api is not None

    def test_import_pdf_splitting_models(self) -> None:
        from apps.pdf_splitting import models
        assert models is not None

    def test_import_job_service(self) -> None:
        from apps.pdf_splitting.services import job_service
        assert job_service is not None
