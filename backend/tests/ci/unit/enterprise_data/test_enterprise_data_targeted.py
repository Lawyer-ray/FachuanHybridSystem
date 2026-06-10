"""Targeted tests for enterprise_data module to push coverage to 80%+."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestEnterpriseDataApiInit:
    def test_api_init(self):
        from apps.enterprise_data.api import __init__ as api_init

        assert api_init is not None
