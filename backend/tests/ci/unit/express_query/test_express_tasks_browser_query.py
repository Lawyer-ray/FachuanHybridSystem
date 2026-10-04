"""express_query.tasks._execute_browser_query 单元测试（mock 浏览器查询与存储）。

覆盖：查询成功后的结果 PDF 落库链路（临时文件 → default_storage →
result_payload/query_url 状态回写）、查询前状态切换、失败时的临时文件清理。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.core.files.base import ContentFile

from apps.express_query import tasks as eq_tasks
from apps.express_query.models import ExpressQueryTaskStatus
from apps.express_query.tasks import _execute_browser_query


class _FakeTempFile:
    """替代 tempfile.NamedTemporaryFile，把临时路径固定在 tmp_path 下。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def __enter__(self) -> SimpleNamespace:
        self._path.write_bytes(b"")
        return SimpleNamespace(name=str(self._path))

    def __exit__(self, *args: object) -> bool:
        return False


@pytest.fixture
def fake_tmp_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tmp_pdf = tmp_path / "express_query_tmp.pdf"
    monkeypatch.setattr(eq_tasks.tempfile, "NamedTemporaryFile", lambda **kwargs: _FakeTempFile(tmp_pdf))
    return tmp_pdf


def _make_task() -> MagicMock:
    task = MagicMock()
    task.id = 11
    task.carrier_type = "sf"
    task.tracking_number = "SF1234567890123"
    return task


class TestExecuteBrowserQuerySuccess:
    def test_full_pipeline(self, fake_tmp_pdf: Path):
        task = _make_task()

        with (
            patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls,
            patch.object(eq_tasks, "default_storage") as storage,
        ):
            svc_cls.return_value.query_and_save_pdf = AsyncMock(return_value="https://track.example/sf")
            svc_cls.disconnect_playwright = AsyncMock()
            storage.save.return_value = "express_query/results/11/abcd1234_SF.pdf"

            _execute_browser_query(task)

            # 浏览器查询参数与 Playwright 连接清理
            svc_cls.return_value.query_and_save_pdf.assert_awaited_once_with(
                carrier_type="sf", tracking_number="SF1234567890123", output_pdf=fake_tmp_pdf
            )
            svc_cls.disconnect_playwright.assert_awaited_once()

            # PDF 经 default_storage 保存（media 落盘走存储服务，路径不可预测化）
            save_args = storage.save.call_args.args
            rel_path, content_file = save_args
            assert rel_path.startswith("express_query/results/11/")
            assert rel_path.rsplit("/", 1)[-1].endswith("SF1234567890123.pdf")
            assert isinstance(content_file, ContentFile)

        assert task.status == ExpressQueryTaskStatus.SUCCESS
        assert task.query_url == "https://track.example/sf"
        assert task.result_pdf.name == "express_query/results/11/abcd1234_SF.pdf"
        assert task.result_payload == {
            "carrier_type": "sf",
            "tracking_number": "SF1234567890123",
            "query_url": "https://track.example/sf",
            "pdf_path": "express_query/results/11/abcd1234_SF.pdf",
        }
        assert task.finished_at is not None
        update_fields = task.save.call_args.kwargs["update_fields"]
        assert {"status", "query_url", "result_pdf", "result_payload", "finished_at"} <= set(update_fields)
        # 临时文件在 finally 中清理
        assert not fake_tmp_pdf.exists()


class TestExecuteBrowserQueryFailure:
    def test_query_error_cleans_tmp_file_and_propagates(self, fake_tmp_pdf: Path):
        task = _make_task()

        with (
            patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls,
            patch.object(eq_tasks, "default_storage") as storage,
        ):
            svc_cls.return_value.query_and_save_pdf = AsyncMock(side_effect=RuntimeError("login expired"))
            svc_cls.disconnect_playwright = AsyncMock()

            with pytest.raises(RuntimeError, match="login expired"):
                _execute_browser_query(task)

            storage.save.assert_not_called()

        # 失败也要清理临时文件、断开 Playwright；save 只发生在 querying 预切换
        assert not fake_tmp_pdf.exists()
        svc_cls.disconnect_playwright.assert_awaited_once()
        assert task.status == ExpressQueryTaskStatus.QUERYING
        assert task.save.call_args.kwargs["update_fields"] == ["status", "updated_at"]

    def test_status_transitions_to_querying_before_query(self, fake_tmp_pdf: Path):
        task = _make_task()
        observed: list[str] = []

        with patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls:

            async def query_and_save_pdf(**kwargs: object) -> str:
                observed.append("query")
                return "https://track.example/ems"

            svc_cls.return_value.query_and_save_pdf = AsyncMock(side_effect=query_and_save_pdf)
            svc_cls.disconnect_playwright = AsyncMock()

            def record_save(**kwargs: object) -> None:
                observed.append(f"save:{task.status}")

            task.save = record_save  # type: ignore[method-assign]
            _execute_browser_query(task)

        # 第一次 save 时任务已进入 querying 状态
        assert observed[0] == "save:querying"
        assert observed[1] == "query"
        assert task.status == ExpressQueryTaskStatus.SUCCESS
