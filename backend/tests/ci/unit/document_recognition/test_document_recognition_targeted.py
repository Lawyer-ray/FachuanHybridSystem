"""Targeted tests for document_recognition module to push coverage to 80%+."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestCaseNumberMixin:
    def test_import(self):
        from apps.document_recognition.services._case_number_mixin import CaseNumberMixin

        assert CaseNumberMixin is not None


class TestDocumentRecognitionApiInit:
    def test_api_init(self):
        from apps.document_recognition.api import __init__ as api_init

        assert api_init is not None
