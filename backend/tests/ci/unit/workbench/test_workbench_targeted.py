"""Targeted tests for workbench module to push coverage to 80%+."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# schemas/workbench_schemas.py (94% coverage)
# ---------------------------------------------------------------------------


class TestWorkbenchSchemas:
    def test_schemas_import(self):
        from apps.workbench.schemas import workbench_schemas

        assert workbench_schemas is not None
