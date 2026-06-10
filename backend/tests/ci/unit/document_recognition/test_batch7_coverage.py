"""Batch7 coverage tests for apps.document_recognition."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestDocumentRecognitionModuleImports:
    """Test that document_recognition module components are importable."""

    def test_import_doc_recognition_admin(self) -> None:
        from apps.document_recognition.admin import document_recognition_admin
        assert document_recognition_admin is not None

    def test_import_doc_recognition_api(self) -> None:
        from apps.document_recognition.api import document_recognition_api
        assert document_recognition_api is not None

    def test_import_doc_recognition_models(self) -> None:
        from apps.document_recognition import models
        assert models is not None

    def test_import_case_number_mixin(self) -> None:
        from apps.document_recognition.services._case_number_mixin import CaseNumberMixin
        assert CaseNumberMixin is not None

    def test_import_datetime_extraction_mixin(self) -> None:
        from apps.document_recognition.services._datetime_extraction_mixin import DatetimeExtractionMixin
        assert DatetimeExtractionMixin is not None
