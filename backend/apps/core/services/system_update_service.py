"""系统更新服务：用于 Admin 一键触发受控 Git 同步。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast
from uuid import uuid4

from django.core.cache import cache

from apps.core.exceptions import ExternalServiceError
from apps.core.infrastructure.subprocess_runner import SubprocessOutput, SubprocessRunner
from apps.core.tasking import TaskSubmissionService

logger = logging.getLogger(__name__)

_SYSTEM_UPDATE_STATE_CACHE_KEY: Final[str] = "core:system_update:state"
_SYSTEM_UPDATE_LOCK_CACHE_KEY: Final[str] = "core:system_update:lock"
_DEFAULT_LOCK_TIMEOUT_SECONDS: Final[int] = 30 * 60
_DEFAULT_TASK_TIMEOUT_SECONDS: Final[int] = 15 * 60
_DEFAULT_STEP_TIMEOUT_SECONDS: Final[int] = 60


class SystemUpdateService:
    """封装系统更新触发、执行与状态管理。"""

    def __init__(
        self,
        *,
        task_submission_service: TaskSubmissionService,
        subprocess_runner: SubprocessRunner | None = None,
        repo_root: Path | None = None,
        default_branch: str = "main",
        lock_timeout_seconds: int = _DEFAULT_LOCK_TIMEOUT_SECONDS,
        task_timeout_seconds: int = _DEFAULT_TASK_TIMEOUT_SECONDS,
        step_timeout_seconds: int = _DEFAULT_STEP_TIMEOUT_SECONDS,
    ) -> None:
        self._task_submission_service = task_submission_service
        self._subprocess_runner = subprocess_runner or SubprocessRunner(allowed_programs={"git", "uv"})
        self._repo_root = repo_root or self._detect_repo_root()
        self._backend_root = self._resolve_backend_root(self._repo_root)
        self._default_branch = default_branch
        self._lock_timeout_seconds = lock_timeout_seconds
        self._task_timeout_seconds = task_timeout_seconds
        self._step_timeout_seconds = step_timeout_seconds

    def trigger_update(self, *, triggered_by: str, enable_post_update_setup: bool = False) -> dict[str, Any]:
        """触发异步更新任务。"""
        current_state = self.get_state()
        if str(current_state.get("status")) in {"queued", "running"}:
            return {
                "accepted": False,
                "message": "已有更新任务在执行，请稍后刷新查看状态。",
                "state": current_state,
            }

        run_id = str(uuid4())
        acquired = bool(cache.add(_SYSTEM_UPDATE_LOCK_CACHE_KEY, run_id, timeout=self._lock_timeout_seconds))
        if not acquired:
            return {
                "accepted": False,
                "message": "系统正在执行另一项更新任务，请稍后重试。",
                "state": self.get_state(),
            }

        options = {"enable_post_update_setup": bool(enable_post_update_setup)}
        base_state = self._build_state(
            run_id=run_id,
            status="queued",
            message="更新任务已提交，等待队列执行。",
            triggered_by=triggered_by,
            started_at=self._now_iso(),
            steps=[],
            options=options,
        )
        self._save_state(base_state)

        try:
            q_task_id = self._task_submission_service.submit(
                "apps.core.services.system_update_service.run_system_update_task",
                kwargs={
                    "run_id": run_id,
                    "triggered_by": triggered_by,
                    "enable_post_update_setup": bool(enable_post_update_setup),
                },
                task_name=f"system_update:{run_id}",
                timeout=self._task_timeout_seconds,
            )
        except Exception as exc:
            self._release_lock(run_id)
            failed_state = self._build_state(
                run_id=run_id,
                status="failed",
                message=f"提交更新任务失败：{exc}",
                triggered_by=triggered_by,
                started_at=base_state["started_at"],
                finished_at=self._now_iso(),
                steps=base_state["steps"],
                options=options,
            )
            self._save_state(failed_state)
            logger.exception("system_update_submit_failed")
            return {
                "accepted": False,
                "message": "更新任务提交失败，请查看日志后重试。",
                "state": failed_state,
            }

        queued_state = self._build_state(
            run_id=run_id,
            status="queued",
            message="更新任务已进入队列。",
            triggered_by=triggered_by,
            q_task_id=q_task_id,
            started_at=base_state["started_at"],
            steps=base_state["steps"],
            options=options,
        )
        self._save_state(queued_state)
        return {
            "accepted": True,
            "message": "更新任务已提交。",
            "state": queued_state,
        }

    def run_update(
        self,
        *,
        run_id: str,
        triggered_by: str,
        enable_post_update_setup: bool = False,
    ) -> dict[str, Any]:
        """在异步任务中执行 Git 同步。"""
        lock_owner = cache.get(_SYSTEM_UPDATE_LOCK_CACHE_KEY)
        if lock_owner not in (None, run_id):
            blocked_state = self._build_state(
                run_id=run_id,
                status="failed",
                message="检测到并发更新任务，当前任务已终止。",
                triggered_by=triggered_by,
                finished_at=self._now_iso(),
                steps=[],
                options={"enable_post_update_setup": bool(enable_post_update_setup)},
            )
            self._save_state(blocked_state)
            return blocked_state

        cache.set(_SYSTEM_UPDATE_LOCK_CACHE_KEY, run_id, timeout=self._lock_timeout_seconds)

        current = self.get_state()
        started_at = str(current.get("started_at") or self._now_iso())
        q_task_id = str(current.get("q_task_id") or "")
        options_obj = current.get("options")
        cached_enable_post_update_setup = False
        if isinstance(options_obj, dict):
            cached_enable_post_update_setup = bool(options_obj.get("enable_post_update_setup"))
        effective_enable_post_update_setup = bool(enable_post_update_setup or cached_enable_post_update_setup)

        steps: list[dict[str, Any]] = []

        running_state = self._build_state(
            run_id=run_id,
            status="running",
            message="正在执行系统更新，请勿重复点击。",
            triggered_by=triggered_by,
            q_task_id=q_task_id,
            started_at=started_at,
            steps=steps,
            options={"enable_post_update_setup": effective_enable_post_update_setup},
        )
        self._save_state(running_state)

        try:
            self._append_step(steps, name="git_fetch", output=self._run_git(["fetch", "origin"]))

            branch_output = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
            self._append_step(steps, name="detect_branch", output=branch_output)
            current_branch = branch_output.stdout.strip() or self._default_branch
            if current_branch == "HEAD":
                current_branch = self._default_branch

            target_branch = self._resolve_pull_branch(current_branch=current_branch, steps=steps)
            pull_output = self._run_git(["pull", "--ff-only", "origin", target_branch])
            self._append_step(steps, name="git_pull", output=pull_output)

            success_message = "系统代码同步完成。"
            if effective_enable_post_update_setup:
                self._append_step(steps, name="uv_sync", output=self._run_uv_sync())
                self._append_step(steps, name="db_migrate", output=self._run_migrate())
                success_message = "系统代码同步与依赖/数据库更新已完成。"

            success_state = self._build_state(
                run_id=run_id,
                status="success",
                message=success_message,
                triggered_by=triggered_by,
                q_task_id=q_task_id,
                started_at=started_at,
                finished_at=self._now_iso(),
                steps=steps,
                options={"enable_post_update_setup": effective_enable_post_update_setup},
            )
            self._save_state(success_state)
            logger.info(
                "system_update_success",
                extra={
                    "run_id": run_id,
                    "requested_branch": current_branch,
                    "pulled_branch": target_branch,
                    "used_branch_fallback": target_branch != current_branch,
                    "enable_post_update_setup": effective_enable_post_update_setup,
                },
            )
            return success_state
        except ExternalServiceError as exc:
            error_state = self._build_state(
                run_id=run_id,
                status="failed",
                message="系统更新失败，请检查执行日志。",
                triggered_by=triggered_by,
                q_task_id=q_task_id,
                started_at=started_at,
                finished_at=self._now_iso(),
                steps=steps,
                error={
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.errors,
                },
                options={"enable_post_update_setup": effective_enable_post_update_setup},
            )
            self._save_state(error_state)
            logger.exception("system_update_failed", extra={"run_id": run_id})
            raise
        finally:
            self._release_lock(run_id)

    def get_state(self) -> dict[str, Any]:
        """读取最新更新状态。"""
        state = cache.get(_SYSTEM_UPDATE_STATE_CACHE_KEY)
        if isinstance(state, dict):
            if "options" not in state:
                state["options"] = {"enable_post_update_setup": False}
            return state
        return self._build_state(
            run_id="",
            status="idle",
            message="暂无更新记录。",
            triggered_by="",
            steps=[],
            options={"enable_post_update_setup": False},
        )

    def _run_git(self, git_args: list[str]) -> SubprocessOutput:
        args = ["git", "-C", str(self._repo_root), *git_args]
        return self._subprocess_runner.run(
            args=args,
            timeout_seconds=float(self._step_timeout_seconds),
            check=True,
        )

    def _resolve_pull_branch(self, *, current_branch: str, steps: list[dict[str, Any]]) -> str:
        if current_branch == self._default_branch:
            return current_branch
        if self._remote_branch_exists(current_branch):
            return current_branch

        fallback_message = f"远端分支 origin/{current_branch} 不存在，已回退为 origin/{self._default_branch}。"
        self._append_step(
            steps,
            name="branch_fallback",
            output=SubprocessOutput(stdout=fallback_message, stderr="", returncode=0),
        )
        return self._default_branch

    def _remote_branch_exists(self, branch: str) -> bool:
        output = self._run_git(["ls-remote", "--heads", "origin", branch])
        return bool(output.stdout.strip())

    def _run_uv_sync(self) -> SubprocessOutput:
        args = ["uv", "sync", "--project", str(self._backend_root)]
        return self._subprocess_runner.run(
            args=args,
            timeout_seconds=float(self._step_timeout_seconds),
            check=True,
        )

    def _run_migrate(self) -> SubprocessOutput:
        args = [
            "uv",
            "run",
            "--project",
            str(self._backend_root),
            "python",
            str(self._backend_root / "manage.py"),
            "migrate",
            "--noinput",
        ]
        return self._subprocess_runner.run(
            args=args,
            timeout_seconds=float(self._step_timeout_seconds),
            check=True,
        )

    def _append_step(self, steps: list[dict[str, Any]], *, name: str, output: SubprocessOutput) -> None:
        steps.append(
            {
                "name": name,
                "status": "success",
                "at": self._now_iso(),
                "returncode": int(output.returncode),
                "stdout": output.stdout,
                "stderr": output.stderr,
            }
        )

    def _save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = self._now_iso()
        cache.set(_SYSTEM_UPDATE_STATE_CACHE_KEY, state, timeout=7 * 24 * 60 * 60)

    def _release_lock(self, run_id: str) -> None:
        current = cache.get(_SYSTEM_UPDATE_LOCK_CACHE_KEY)
        if current == run_id:
            cache.delete(_SYSTEM_UPDATE_LOCK_CACHE_KEY)

    def _build_state(
        self,
        *,
        run_id: str,
        status: str,
        message: str,
        triggered_by: str,
        steps: list[dict[str, Any]],
        q_task_id: str = "",
        started_at: str | None = None,
        finished_at: str | None = None,
        error: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "status": status,
            "message": message,
            "triggered_by": triggered_by,
            "q_task_id": q_task_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "steps": steps,
            "error": error or {},
            "options": options or {"enable_post_update_setup": False},
            "updated_at": self._now_iso(),
            "repo_root": str(self._repo_root),
        }

    def _detect_repo_root(self) -> Path:
        current = Path(__file__).resolve()
        for parent in (current, *current.parents):
            if (parent / ".git").exists():
                return parent
        return current.parents[4]

    @staticmethod
    def _resolve_backend_root(repo_root: Path) -> Path:
        backend_root = repo_root / "backend"
        if backend_root.exists():
            return backend_root
        return repo_root

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=UTC).isoformat()


def run_system_update_task(
    *,
    run_id: str,
    triggered_by: str,
    enable_post_update_setup: bool = False,
) -> dict[str, Any]:
    """供 Django-Q 调用的入口函数。"""
    from apps.core.dependencies import build_system_update_service

    service = cast(SystemUpdateService, build_system_update_service())
    return service.run_update(
        run_id=run_id,
        triggered_by=triggered_by,
        enable_post_update_setup=enable_post_update_setup,
    )
