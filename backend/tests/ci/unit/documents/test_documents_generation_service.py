"""documents/services/generation/generation_service.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.documents.services.generation.generation_service import (
    ConfigValidationResult,
    GenerationService,
    _CONFIG_TYPE_GENERATION_RULE,
)


class TestConfigValidationResult:
    """ConfigValidationResult 数据类测试。"""

    def test_valid(self) -> None:
        r = ConfigValidationResult(is_valid=True)
        assert r.is_valid is True
        assert r.error == ""

    def test_invalid_with_error(self) -> None:
        r = ConfigValidationResult(is_valid=False, error="模板不存在")
        assert r.is_valid is False
        assert r.error == "模板不存在"


class TestGenerationServiceApplyValueUpdates:
    """_apply_value_updates 测试。"""

    def setup_method(self) -> None:
        self.svc = GenerationService()

    def test_updates_case_type(self) -> None:
        value = {"case_type": "old"}
        self.svc._apply_value_updates(value, {"case_type": "new"})
        assert value["case_type"] == "new"

    def test_empty_folder_path_raises(self) -> None:
        value: dict = {}
        with pytest.raises(Exception) as exc_info:
            self.svc._apply_value_updates(value, {"folder_path": "  "})
        assert "文件夹路径不能为空" in str(exc_info.value)

    def test_valid_folder_path(self) -> None:
        value: dict = {}
        self.svc._apply_value_updates(value, {"folder_path": " /path/to/folder "})
        assert value["folder_path"] == "/path/to/folder"

    def test_none_values_skipped(self) -> None:
        value = {"case_type": "original"}
        self.svc._apply_value_updates(value, {"case_type": None})
        assert value["case_type"] == "original"

    def test_missing_keys_skipped(self) -> None:
        value = {"case_type": "original"}
        self.svc._apply_value_updates(value, {})
        assert value["case_type"] == "original"

    def test_priority_updated(self) -> None:
        value: dict = {}
        self.svc._apply_value_updates(value, {"priority": 5})
        assert value["priority"] == 5

    def test_condition_updated(self) -> None:
        value: dict = {}
        cond = {"field": "value"}
        self.svc._apply_value_updates(value, {"condition": cond})
        assert value["condition"] == cond


class TestGenerationServiceDeleteConfig:
    """delete_generation_config 测试。"""

    def setup_method(self) -> None:
        self.svc = GenerationService()

    @patch("apps.documents.services.generation.generation_service.GenerationConfig")
    def test_delete_existing(self, MockConfig: MagicMock) -> None:
        config = MagicMock()
        MockConfig.objects.filter.return_value.first.return_value = config
        result = self.svc.delete_generation_config(1)
        assert result is True
        assert config.is_active is False
        config.save.assert_called_once()

    @patch("apps.documents.services.generation.generation_service.GenerationConfig")
    def test_delete_nonexistent(self, MockConfig: MagicMock) -> None:
        MockConfig.objects.filter.return_value.first.return_value = None
        result = self.svc.delete_generation_config(999)
        assert result is False


class TestGenerationServiceValidateConfigReferences:
    """validate_config_references 测试。"""

    def setup_method(self) -> None:
        self.svc = GenerationService()

    @patch("apps.documents.services.generation.generation_service.DocumentTemplate")
    def test_no_template_id(self, MockTemplate: MagicMock) -> None:
        config = MagicMock()
        config.document_template_id = None
        valid, msg = self.svc.validate_config_references(config)
        assert valid is False
        assert "未关联" in msg

    @patch("apps.documents.services.generation.generation_service.DocumentTemplate")
    def test_template_not_found(self, MockTemplate: MagicMock) -> None:
        config = MagicMock()
        config.document_template_id = 1
        MockTemplate.objects.filter.return_value.first.return_value = None
        valid, msg = self.svc.validate_config_references(config)
        assert valid is False
        assert "不存在" in msg

    @patch("apps.documents.services.generation.generation_service.DocumentTemplate")
    def test_template_inactive(self, MockTemplate: MagicMock) -> None:
        config = MagicMock()
        config.document_template_id = 1
        template = MagicMock()
        template.is_active = False
        MockTemplate.objects.filter.return_value.first.return_value = template
        valid, msg = self.svc.validate_config_references(config)
        assert valid is False
        assert "禁用" in msg

    @patch("apps.documents.services.generation.generation_service.DocumentTemplate")
    def test_valid_reference(self, MockTemplate: MagicMock) -> None:
        config = MagicMock()
        config.document_template_id = 1
        template = MagicMock()
        template.is_active = True
        MockTemplate.objects.filter.return_value.first.return_value = template
        valid, msg = self.svc.validate_config_references(config)
        assert valid is True
        assert msg == ""


class TestGenerationServiceUpdateTaskStatus:
    """update_task_status 测试。"""

    def setup_method(self) -> None:
        self.svc = GenerationService()

    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_task_not_found(self, MockTask: MagicMock) -> None:
        MockTask.objects.filter.return_value.first.return_value = None
        with pytest.raises(Exception) as exc_info:
            self.svc.update_task_status(1, "completed")
        assert "不存在" in str(exc_info.value)

    @patch("apps.documents.services.generation.generation_service.GenerationTask")
    def test_invalid_status_raises(self, MockTask: MagicMock) -> None:
        task = MagicMock()
        MockTask.objects.filter.return_value.first.return_value = task
        with patch("apps.documents.models.GenerationStatus") as MockStatus:
            MockStatus.choices = [("pending", "P"), ("completed", "C")]
            with pytest.raises(Exception) as exc_info:
                self.svc.update_task_status(1, "invalid_status")
            assert "无效" in str(exc_info.value)


class TestGenerationServiceGenerate:
    """generate 方法测试。"""

    def test_no_case_raises(self) -> None:
        svc = GenerationService()
        task = MagicMock()
        task.case_id = None
        with pytest.raises(Exception) as exc_info:
            svc.generate(task)
        assert "未关联案件" in str(exc_info.value)

    def test_with_case_raises_not_implemented(self) -> None:
        svc = GenerationService()
        task = MagicMock()
        task.case_id = 1
        with pytest.raises(NotImplementedError):
            svc.generate(task)


class TestConfigTypeConstant:
    def test_value(self) -> None:
        assert _CONFIG_TYPE_GENERATION_RULE == "generation_rule"
