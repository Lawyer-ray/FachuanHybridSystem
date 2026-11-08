"""express_query.tasks._execute_browser_query 单元测试（mock 浏览器查询与存储）。

覆盖：会话解析与登录态门禁、查询成功后的结果 PDF 落库链路（临时文件 →
default_storage → result_payload/query_url 状态回写）、查询前状态切换、
失败时的临时文件清理。
"""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.core.files.base import ContentFile

from apps.express_query import tasks as eq_tasks
from apps.express_query.models import ExpressQueryTaskStatus, ExpressSessionStatus
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


def _active_session() -> MagicMock:
    session = MagicMock()
    session.id = 7
    session.profile_key = "sf_1"
    session.status = ExpressSessionStatus.ACTIVE
    session.is_ready = True
    return session


@pytest.fixture
def ready_session():
    """默认给一个已登录会话，避免测试都落到「等待登录」分支。"""
    session = _active_session()
    with (
        patch.object(eq_tasks, "resolve_session", return_value=session),
        patch.object(eq_tasks, "session_lock", lambda _s: nullcontext()),
    ):
        yield session


class TestExecuteBrowserQuerySuccess:
    def test_full_pipeline(self, fake_tmp_pdf: Path, ready_session):
        task = _make_task()

        with (
            patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls,
            patch.object(eq_tasks, "default_storage") as storage,
        ):
            svc_cls.return_value.query_and_save_pdf = AsyncMock(return_value="https://track.example/sf")
            storage.save.return_value = "express_query/results/11/abcd1234_SF.pdf"

            _execute_browser_query(task)

            # 浏览器查询参数：带上会话的 profile_key，且无人值守（不交互等待扫码）
            svc_cls.return_value.query_and_save_pdf.assert_awaited_once_with(
                carrier_type="sf",
                tracking_number="SF1234567890123",
                output_pdf=fake_tmp_pdf,
                profile_key="sf_1",
                allow_interactive_login=False,
            )
            # PDF 经 default_storage 保存（media 落盘走存储服务，路径不可预测化）
            rel_path, content_file = storage.save.call_args.args
            assert rel_path.startswith("express_query/results/11/")
            assert isinstance(content_file, ContentFile)


class TestSessionGating:
    """登录态门禁：无可用会话时不得启动浏览器。"""

    def test_missing_session_switches_to_waiting_login(self, fake_tmp_pdf: Path):
        task = _make_task()
        pending = _active_session()
        pending.is_ready = False
        pending.status = ExpressSessionStatus.EMPTY

        with (
            patch.object(eq_tasks, "resolve_session", return_value=pending),
            patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls,
        ):
            _execute_browser_query(task)

        svc_cls.assert_not_called()
        assert task.status == ExpressQueryTaskStatus.WAITING_LOGIN
        assert "扫码" in task.error_message

    def test_login_required_exception_marks_expired(self, fake_tmp_pdf: Path, ready_session):
        from apps.express_query.services.browser_query.sf_query_handler import ExpressLoginRequired

        task = _make_task()

        with (
            patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls,
            patch.object(eq_tasks, "mark_login_expired") as expired,
        ):
            svc_cls.return_value.query_and_save_pdf = AsyncMock(side_effect=ExpressLoginRequired("未登录"))

            _execute_browser_query(task)

        expired.assert_called_once()
        assert task.status == ExpressQueryTaskStatus.WAITING_LOGIN


class TestExecuteBrowserQueryFailure:
    def test_query_error_cleans_tmp_file_and_propagates(self, fake_tmp_pdf: Path, ready_session):
        task = _make_task()

        with (
            patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls,
            patch.object(eq_tasks, "default_storage") as storage,
        ):
            svc_cls.return_value.query_and_save_pdf = AsyncMock(side_effect=RuntimeError("boom"))

            with pytest.raises(RuntimeError, match="boom"):
                _execute_browser_query(task)

            storage.save.assert_not_called()

        # 失败也要清理临时文件；save 只发生在 querying 预切换
        assert not fake_tmp_pdf.exists()
        assert task.status == ExpressQueryTaskStatus.QUERYING

    def test_status_transitions_to_querying_before_query(self, fake_tmp_pdf: Path, ready_session):
        task = _make_task()
        observed: list[str] = []

        with patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls:

            async def query_and_save_pdf(**kwargs: object) -> str:
                observed.append("query")
                return "https://track.example/ems"

            svc_cls.return_value.query_and_save_pdf = AsyncMock(side_effect=query_and_save_pdf)

            def record_save(**kwargs: object) -> None:
                observed.append(f"save:{task.status}")

            task.save = record_save  # type: ignore[method-assign]
            _execute_browser_query(task)

        # 第一次 save 时任务已进入 querying 状态
        assert observed[0] == "save:querying"
        assert observed[1] == "query"
        assert task.status == ExpressQueryTaskStatus.SUCCESS


class TestBrowserLifetimeIsSelfManaged:
    """浏览器生命周期由 query_and_save_pdf 内的 async with 自包含。

    历史教训：把浏览器实例 / async context manager 跨 asyncio.run() 边界持有，
    会让收尾的 shutdown_asyncgens 永久阻塞，任务卡在"查询中"直到 600s 超时。
    """

    def test_tasks_does_not_hold_browser_manager(self) -> None:
        assert not hasattr(eq_tasks, "disconnect_playwright")

    def test_successful_run_completes(self, fake_tmp_pdf: Path, ready_session):
        task = _make_task()

        with (
            patch.object(eq_tasks, "ExpressBrowserQueryService") as svc_cls,
            patch.object(eq_tasks, "default_storage") as storage,
        ):
            svc_cls.return_value.query_and_save_pdf = AsyncMock(return_value="https://track.example/sf")
            storage.save.return_value = "express_query/results/11/abcd1234_SF.pdf"

            _execute_browser_query(task)

        assert task.status == ExpressQueryTaskStatus.SUCCESS
