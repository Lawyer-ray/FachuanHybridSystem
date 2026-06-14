"""Tests for workflow/management/commands/seed_workflow_templates.py (0% coverage).

Covers: Command.handle — creating and updating templates.
"""
from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestSeedWorkflowTemplates:
    def test_creates_new_template(self):
        from apps.workflow.management.commands.seed_workflow_templates import Command

        cmd = Command()
        cmd.stdout = StringIO()

        with patch("apps.workflow.management.commands.seed_workflow_templates.WorkflowTemplate") as MockTpl:
            MockTpl.objects.update_or_create.return_value = (
                SimpleNamespace(name="买卖合同纠纷(测试)", slug="sales-contract-dispute-test"),
                True,  # created
            )
            cmd.handle()

        assert "创建" in cmd.stdout.getvalue()
        MockTpl.objects.update_or_create.assert_called_once()

    def test_updates_existing_template(self):
        from apps.workflow.management.commands.seed_workflow_templates import Command

        cmd = Command()
        cmd.stdout = StringIO()

        with patch("apps.workflow.management.commands.seed_workflow_templates.WorkflowTemplate") as MockTpl:
            MockTpl.objects.update_or_create.return_value = (
                SimpleNamespace(name="买卖合同纠纷(测试)", slug="sales-contract-dispute-test"),
                False,  # not created (updated)
            )
            cmd.handle()

        assert "更新" in cmd.stdout.getvalue()

    def test_template_config_has_correct_slug(self):
        from apps.workflow.management.commands.seed_workflow_templates import Command

        cmd = Command()
        cmd.stdout = StringIO()

        with patch("apps.workflow.management.commands.seed_workflow_templates.WorkflowTemplate") as MockTpl:
            MockTpl.objects.update_or_create.return_value = (
                SimpleNamespace(name="Test", slug="test"),
                True,
            )
            cmd.handle()

            call_kwargs = MockTpl.objects.update_or_create.call_args
            assert call_kwargs[1]["slug"] == "sales-contract-dispute-test"
            defaults = call_kwargs[1]["defaults"]
            assert defaults["is_active"] is True
            assert defaults["temporal_workflow_name"] == "SalesContractDisputeWorkflow"
            assert len(defaults["steps_schema"]) == 4
