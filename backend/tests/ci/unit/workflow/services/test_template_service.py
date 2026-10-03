"""WorkflowTemplateService 单测：slug 去重、白名单三态、duplicate 复审、404 路径。

从 api/workflow_api.py 下沉后的回归锚点（原 API 层 mock 测试语义的延续）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.workflow.schemas.workflow_schemas import StepConfigIn, TemplateCreateIn, TemplateUpdateIn
from apps.workflow.services import get_workflow_template_service

_SVC = "apps.workflow.services.template_service"


def _step(**kwargs: Any) -> StepConfigIn:
    base: dict[str, Any] = {"id": "s1", "name": "s", "type": "activity"}
    base.update(kwargs)
    return StepConfigIn(**base)


class TestUniqueSlug:
    def test_plain_dedup_counter(self):
        svc = get_workflow_template_service()
        with patch(f"{_SVC}.WorkflowTemplate") as MockModel:
            MockModel.objects.filter.return_value.exists.side_effect = [True, True, False]
            assert svc._unique_slug("base") == "base-2"

    def test_copy_mode_dedup(self):
        svc = get_workflow_template_service()
        with patch(f"{_SVC}.WorkflowTemplate") as MockModel:
            MockModel.objects.filter.return_value.exists.side_effect = [True, False]
            assert svc._unique_slug("base", copy_mode=True) == "base-copy-1"


class TestWhitelistInService:
    def test_create_validates_steps(self):
        svc = get_workflow_template_service()
        with pytest.raises(ValidationException):
            svc.create_template(
                TemplateCreateIn(name="x", category="litigation", steps=[_step(type="code")])
            )

    def test_update_validates_steps(self):
        svc = get_workflow_template_service()
        with patch(f"{_SVC}.WorkflowTemplate") as MockModel:
            MockModel.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockModel.objects.get.return_value = MagicMock(id=1, name="t")
            with pytest.raises(ValidationException):
                svc.update_template(
                    1, TemplateUpdateIn(steps=[_step(type="http")]), user=MagicMock(is_superuser=False)
                )


class TestDuplicateRecheck:
    def test_duplicate_blocked_for_legacy_dangerous_template(self):
        """复审关键用例：存量危险模板（含 code 步骤）不得经复制繁殖。"""
        svc = get_workflow_template_service()
        source = MagicMock(slug="s", name="n", steps_schema=[{"type": "code", "mcp_tool": ""}])
        with patch(f"{_SVC}.WorkflowTemplate") as MockModel:
            MockModel.objects.get.return_value = source
            with pytest.raises(ValidationException):
                svc.duplicate_template(1, user=MagicMock(is_superuser=True))


class TestNotFound:
    @pytest.mark.parametrize("method,args", [("get_template", (1,)), ("delete_template", (1,))])
    def test_raises_not_found(self, method, args):
        svc = get_workflow_template_service()
        with patch(f"{_SVC}.WorkflowTemplate") as MockModel:
            MockModel.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockModel.objects.get.side_effect = MockModel.DoesNotExist
            with pytest.raises(NotFoundError):
                getattr(svc, method)(*args)
