"""异步解析任务调度服务测试（parsing_api 下沉的创建 + 提交逻辑）."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.document_parsing.services.task_dispatch_service import DocumentParsingTaskDispatchService


def _kwargs() -> dict[str, object]:
    return {
        "file_name": "contract.pdf",
        "file_path": Path("/tmp/uploads/contract.pdf"),
        "file_size": 1024,
        "backend": "mineru",
        "extract_tables": True,
        "extract_images": False,
        "return_markdown": True,
        "created_by": None,
    }


class TestSubmitParseTask:
    @pytest.mark.asyncio
    async def test_creates_record_then_submits_with_convention(self):
        created = MagicMock()
        created.id = 42

        with (
            patch("apps.document_parsing.services.task_dispatch_service.DocumentParsingTask") as mock_model,
            patch(
                "apps.document_parsing.services.task_dispatch_service.submit_task",
                return_value="task-abc",
            ) as mock_submit,
        ):
            mock_model.objects.create = MagicMock(return_value=created)

            task_id = await DocumentParsingTaskDispatchService().submit_parse_task(**_kwargs())  # type: ignore[arg-type]

        assert task_id == "task-abc"
        # 1) 先建解析记录：状态 PROCESSING、归属人落库
        mock_model.objects.create.assert_called_once()
        call_kwargs = mock_model.objects.create.call_args.kwargs
        assert call_kwargs["file_name"] == "contract.pdf"
        assert call_kwargs["file_path"] == "/tmp/uploads/contract.pdf"
        assert call_kwargs["status"] == mock_model.Status.PROCESSING
        # 2) 再提交后台任务：约定的 task_name / hook / 超时与 target
        submit_kwargs = mock_submit.call_args.kwargs
        assert submit_kwargs["task_name"] == "document_parsing_42"
        assert submit_kwargs["hook"] == "apps.document_parsing.tasks.document_parsing_hook"
        assert submit_kwargs["timeout"] == 600
        assert mock_submit.call_args.args[0] == "apps.document_parsing.tasks.execute_parse_document"
        assert mock_submit.call_args.args[2] == "pdf"  # 扩展名去点

    @pytest.mark.asyncio
    async def test_record_creation_failure_propagates(self):
        with (
            patch("apps.document_parsing.services.task_dispatch_service.DocumentParsingTask") as mock_model,
            patch(
                "apps.document_parsing.services.task_dispatch_service.submit_task",
            ) as mock_submit,
        ):
            mock_model.objects.create = MagicMock(side_effect=RuntimeError("db down"))

            with pytest.raises(RuntimeError, match="db down"):
                await DocumentParsingTaskDispatchService().submit_parse_task(**_kwargs())  # type: ignore[arg-type]

        # 记录创建失败时不得提交后台任务
        mock_submit.assert_not_called()
