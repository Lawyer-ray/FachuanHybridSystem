"""Batch7 coverage tests for apps.workbench."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestWorkbenchModuleImports:
    """Test that workbench module components are importable."""

    def test_import_workbench_agents_definitions(self) -> None:
        from apps.workbench.agents import definitions
        assert definitions is not None

    def test_import_workbench_api(self) -> None:
        from apps.workbench.api import workbench_api
        assert workbench_api is not None

    def test_import_workbench_app(self) -> None:
        from apps.workbench.apps import WorkbenchConfig
        assert WorkbenchConfig is not None
