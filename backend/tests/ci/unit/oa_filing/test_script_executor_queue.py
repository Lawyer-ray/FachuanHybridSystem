"""ScriptExecutorService 排队上限单测（容量死锁修复的行为锚点）。

回归语义：共享 2-worker 池的排队名额（4 个）占满时，新任务立即把会话置
FAILED 并抛 ScriptExecutionError——不再是无限静默排队（进程重启即丢）；
任务开始执行后名额释放，不占用运行时长。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.oa_filing.services import script_executor_service as mod
from apps.oa_filing.services.exceptions import ScriptExecutionError


@pytest.fixture(autouse=True)
def _fresh_semaphore(monkeypatch: pytest.MonkeyPatch):
    """每例重置模块级信号量，避免用例间名额泄漏。"""
    monkeypatch.setattr(mod, "_queued_slots", mod.threading.Semaphore(mod._MAX_QUEUED_JOBS))
    yield


def _make_session_model() -> tuple[MagicMock, MagicMock]:
    session_model = MagicMock()
    session = MagicMock()
    session_model.objects.filter.return_value.update.return_value = 1
    return session_model, session


class TestSubmitSessionJob:
    def test_normal_path_submits_wrapped(self):
        session_model, _ = _make_session_model()
        fn = MagicMock()
        with patch.object(mod, "_executor") as executor:
            mod._submit_session_job(session_model, 1, "FAILED", "立案", fn, "a", "b")
        executor.submit.assert_called_once()
        submitted_fn = executor.submit.call_args.args[0]
        # wrapper 开始执行时先释放名额再跑任务
        fn.reset_mock()
        with patch.object(mod._queued_slots, "release") as release:
            submitted_fn("a", "b")
        release.assert_called_once()
        fn.assert_called_once_with("a", "b")

    def test_queue_full_marks_session_failed_and_raises(self):
        """排队名额占满 → 会话立即置 FAILED + 抛 ScriptExecutionError。"""
        session_model, _ = _make_session_model()
        # 占满全部名额（不释放）
        for _ in range(mod._MAX_QUEUED_JOBS):
            assert mod._queued_slots.acquire(blocking=False)
        with pytest.raises(ScriptExecutionError, match="排队已满"):
            mod._submit_session_job(session_model, 99, "FAILED", "立案", MagicMock())
        session_model.objects.filter.assert_called_once_with(pk=99)
        update_kwargs = session_model.objects.filter.return_value.update.call_args.kwargs
        assert update_kwargs["status"] == "FAILED"
        assert "排队已满" in update_kwargs["error_message"]

    def test_submit_failure_releases_slot(self):
        """executor.submit 本身抛错时名额必须归还，否则泄漏一个永久名额。"""
        session_model, _ = _make_session_model()
        with patch.object(mod, "_executor") as executor:
            executor.submit.side_effect = RuntimeError("executor down")
            with pytest.raises(RuntimeError, match="executor down"):
                mod._submit_session_job(session_model, 1, "FAILED", "立案", MagicMock())
        # 名额应已归还：可以再成功占满 MAX 个
        for _ in range(mod._MAX_QUEUED_JOBS):
            assert mod._queued_slots.acquire(blocking=False)

    def test_execute_wires_queue_guard(self, db: Any) -> None:
        """execute()（立案入口）经由 _submit_session_job 走排队守卫。"""
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService

        svc = ScriptExecutorService()
        fake_credential = MagicMock()
        with (
            patch.object(mod, "_ensure_contract_access"),
            patch.object(
                mod.ScriptExecutorService, "_find_credential", staticmethod(lambda user, site: fake_credential)
            ),
            patch.object(mod, "_submit_session_job") as submit_job,
            patch("apps.oa_filing.models.FilingSession") as session_model,
        ):
            session_model.objects.create.return_value = MagicMock(pk=7, id=7)
            session_model.objects.get.return_value = MagicMock(pk=7)
            svc.execute("金诚同达OA", contract_id=1, case_id=None, user=MagicMock())
        submit_job.assert_called_once()
        assert submit_job.call_args.args[1] == 7  # session_id
