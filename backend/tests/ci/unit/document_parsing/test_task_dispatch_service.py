"""异步解析任务调度服务测试（parsing_api 下沉的创建 + 提交逻辑）.

安全修复后的契约：对外返回 DocumentParsingTask 记录 id（字符串），
Django-Q 原始 id 回写记录的 q_task_id 供轮询端点内部反查。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from apps.document_parsing.models import DocumentParsingTask
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
                return_value="q-uuid-abc",
            ) as mock_submit,
        ):
            mock_model.objects.create = MagicMock(return_value=created)
            mock_model.objects.filter = MagicMock(return_value=MagicMock(update=MagicMock(return_value=1)))

            task_id = await DocumentParsingTaskDispatchService().submit_parse_task(**_kwargs())  # type: ignore[arg-type]

        # 安全修复：对外令牌 = 记录 id（字符串），不再是 Q 原始 id
        assert task_id == "42"
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
        # 3) Q id 回写记录 q_task_id（供轮询端点内部反查）
        mock_model.objects.filter.assert_called_once_with(pk=42)
        mock_model.objects.filter.return_value.update.assert_called_once_with(q_task_id="q-uuid-abc")

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

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_submit_persists_record_and_q_task_id(self):
        """提交后 DB 里记录可见：id 令牌可反查、q_task_id 已回写。

        注意：service 内 sync_to_async 在独立线程连接上执行 ORM，不进入
        pytest-django 测试事务，结束时需自行清理，避免污染 reuse-db 库。
        """
        cleanup = sync_to_async(
            lambda: DocumentParsingTask.objects.filter(file_name__in=["contract.pdf"]).delete(),
            thread_sensitive=False,
        )
        await cleanup()
        try:
            with patch(
                "apps.document_parsing.services.task_dispatch_service.submit_task",
                return_value="q-real-1",
            ) as mock_submit:
                task_id = await DocumentParsingTaskDispatchService().submit_parse_task(**_kwargs())  # type: ignore[arg-type]

            assert task_id.isdigit()
            fetch = sync_to_async(DocumentParsingTask.objects.get, thread_sensitive=False)
            record = await fetch(pk=int(task_id))
            assert record.q_task_id == "q-real-1"
            assert record.status == DocumentParsingTask.Status.PROCESSING
            assert mock_submit.call_args.kwargs["task_name"] == f"document_parsing_{record.pk}"
        finally:
            await cleanup()


class TestSubmitExtractTextTask:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_creates_record_returns_record_id_and_persists_q_task_id(self):
        """extract-text 异步路径同模式：建记录、hook 约定、返回记录 id。

        同上：跨线程连接写入需自行清理。
        """
        cleanup = sync_to_async(
            lambda: DocumentParsingTask.objects.filter(file_name__in=["note.docx"]).delete(),
            thread_sensitive=False,
        )
        await cleanup()
        try:
            with patch(
                "apps.document_parsing.services.task_dispatch_service.submit_task",
                return_value="q-real-2",
            ) as mock_submit:
                task_id = await DocumentParsingTaskDispatchService().submit_extract_text_task(
                    file_name="note.docx",
                    file_path=Path("/tmp/uploads/note.docx"),
                    file_size=2048,
                    backend="textin",
                    max_length=500,
                    created_by=None,
                )

            assert task_id.isdigit()
            fetch = sync_to_async(DocumentParsingTask.objects.get, thread_sensitive=False)
            record = await fetch(pk=int(task_id))
            assert record.q_task_id == "q-real-2"
            assert record.file_name == "note.docx"
            assert mock_submit.call_args.args[0] == "apps.document_parsing.tasks.execute_extract_text"
            assert mock_submit.call_args.args[2:] == ("textin", 500)
            assert mock_submit.call_args.kwargs["task_name"] == f"document_parsing_{record.pk}"
            assert mock_submit.call_args.kwargs["hook"] == "apps.document_parsing.tasks.document_parsing_hook"
        finally:
            await cleanup()
