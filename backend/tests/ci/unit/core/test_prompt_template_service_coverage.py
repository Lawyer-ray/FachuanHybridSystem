"""apps/core/services/prompt_template_service.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.prompt_template_service import sync_prompt_templates


def _make_template(name: str, template: str = "Hello {name}") -> MagicMock:
    """创建模拟 PromptTemplate 条目。"""
    item = MagicMock()
    item.name = name
    item.description = f"Description for {name}"
    item.template = template
    item.variables = ["name"]
    return item


class TestSyncPromptTemplates:
    """测试 sync_prompt_templates。"""

    @patch("apps.core.services.prompt_template_service.transaction")
    @patch("apps.core.models.PromptTemplate")
    @patch("apps.core.llm.prompts.PromptManager")
    def test_sync_with_overwrite_updates_existing(
        self, mock_manager: MagicMock, mock_model: MagicMock, mock_txn: MagicMock
    ) -> None:
        """overwrite=True 时使用 update_or_create。"""
        mock_manager._templates = {
            "greeting": _make_template("greeting"),
        }

        mock_txn.atomic.return_value.__enter__ = MagicMock()
        mock_txn.atomic.return_value.__exit__ = MagicMock()
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        result = sync_prompt_templates(overwrite=True)

        mock_model.objects.update_or_create.assert_called_once()
        assert result["synced_count"] == 1

    @patch("apps.core.services.prompt_template_service.transaction")
    @patch("apps.core.models.PromptTemplate")
    @patch("apps.core.llm.prompts.PromptManager")
    def test_sync_without_overwrite_uses_get_or_create(
        self, mock_manager: MagicMock, mock_model: MagicMock, mock_txn: MagicMock
    ) -> None:
        """overwrite=False 时使用 get_or_create，仅计数新增项。"""
        mock_manager._templates = {
            "greeting": _make_template("greeting"),
        }

        mock_txn.atomic.return_value.__enter__ = MagicMock()
        mock_txn.atomic.return_value.__exit__ = MagicMock()
        mock_model.objects.get_or_create.return_value = (MagicMock(), True)

        result = sync_prompt_templates(overwrite=False)

        mock_model.objects.get_or_create.assert_called_once()
        assert result["synced_count"] == 1

    @patch("apps.core.services.prompt_template_service.transaction")
    @patch("apps.core.models.PromptTemplate")
    @patch("apps.core.llm.prompts.PromptManager")
    def test_sync_without_overwrite_not_counting_existing(
        self, mock_manager: MagicMock, mock_model: MagicMock, mock_txn: MagicMock
    ) -> None:
        """overwrite=False 且模板已存在（created=False）时不应计数。"""
        mock_manager._templates = {
            "greeting": _make_template("greeting"),
        }

        mock_txn.atomic.return_value.__enter__ = MagicMock()
        mock_txn.atomic.return_value.__exit__ = MagicMock()
        mock_model.objects.get_or_create.return_value = (MagicMock(), False)

        result = sync_prompt_templates(overwrite=False)

        assert result["synced_count"] == 0

    @patch("apps.core.services.prompt_template_service.transaction")
    @patch("apps.core.models.PromptTemplate")
    @patch("apps.core.llm.prompts.PromptManager")
    def test_sync_multiple_templates(
        self, mock_manager: MagicMock, mock_model: MagicMock, mock_txn: MagicMock
    ) -> None:
        """多个模板时应分别处理。"""
        mock_manager._templates = {
            "greeting": _make_template("greeting"),
            "farewell": _make_template("farewell"),
            "question": _make_template("question"),
        }

        mock_txn.atomic.return_value.__enter__ = MagicMock()
        mock_txn.atomic.return_value.__exit__ = MagicMock()
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        result = sync_prompt_templates(overwrite=True)

        assert mock_model.objects.update_or_create.call_count == 3
        assert result["synced_count"] == 3

    @patch("apps.core.services.prompt_template_service.transaction")
    @patch("apps.core.models.PromptTemplate")
    @patch("apps.core.llm.prompts.PromptManager")
    def test_returns_dict_with_synced_count(
        self, mock_manager: MagicMock, mock_model: MagicMock, mock_txn: MagicMock
    ) -> None:
        """返回值应为包含 synced_count 的字典。"""
        mock_manager._templates = {}

        mock_txn.atomic.return_value.__enter__ = MagicMock()
        mock_txn.atomic.return_value.__exit__ = MagicMock()

        result = sync_prompt_templates(overwrite=True)

        assert isinstance(result, dict)
        assert "synced_count" in result
        assert result["synced_count"] == 0

    @patch("apps.core.services.prompt_template_service.transaction")
    @patch("apps.core.models.PromptTemplate")
    @patch("apps.core.llm.prompts.PromptManager")
    def test_category_extracted_from_name(
        self, mock_manager: MagicMock, mock_model: MagicMock, mock_txn: MagicMock
    ) -> None:
        """category 应从模板名称的第一个下划线前段提取。"""
        mock_manager._templates = {
            "litigation_complaint": _make_template("litigation_complaint"),
        }

        mock_txn.atomic.return_value.__enter__ = MagicMock()
        mock_txn.atomic.return_value.__exit__ = MagicMock()
        mock_model.objects.update_or_create.return_value = (MagicMock(), True)

        sync_prompt_templates(overwrite=True)

        call_kwargs = mock_model.objects.update_or_create.call_args
        defaults = call_kwargs.kwargs.get("defaults") or call_kwargs[1].get("defaults")
        assert defaults["category"] == "litigation"
