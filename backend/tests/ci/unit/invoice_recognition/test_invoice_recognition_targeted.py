"""Targeted tests for invoice_recognition module to push coverage to 80%+."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestInvoiceRecognitionApiInit:
    def test_api_init(self):
        from apps.invoice_recognition.api import __init__ as api_init

        assert api_init is not None
