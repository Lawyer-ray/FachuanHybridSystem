"""图片旋转「历史任务」端点的接线测试（2026-11-23 审计回归）。

## 背景

`apps/image_rotation/services/job_service.py` 里的 `ImageRotationJobService`
在「静态方法下沉」清理后变成**空类**（类体只剩注释），而 API 层仍在
`ImageRotationJobService().list_jobs(...)` / `.get_job(...)` / `.delete_job(...)`，
导致 8 个 `/api/v1/image-rotation/jobs*` 端点必然 `AttributeError` → 500。
这些端点全部带 `# pragma: no cover`，所以单测与覆盖率都看不见它。

同时：`get_job` / `list_jobs` / `get_job_detail` / `arun_ocr` / `delete_job`
都支持 `user=` 属主收敛（安全审计 2026-10-19 加的），但 API 层**从未传 user**，
等于把那次安全修复架空了——任意登录用户可按 job_id 读/改/删他人任务。

本文件同时守这两条：
1. API 依赖的服务符号必须真实存在且可调用（防止再次出现空壳类）；
2. 每个端点必须把当前用户传下去（防止属主过滤再次被架空）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from apps.image_rotation.api import image_rotation_api as api


def _request(user: Any = None) -> Any:
    if user is None:
        user = SimpleNamespace(is_authenticated=True, is_superuser=False, pk=7)
    return SimpleNamespace(user=user)


def _anonymous_request() -> Any:
    return SimpleNamespace(user=SimpleNamespace(is_authenticated=False))


def test_job_service_module_exposes_every_symbol_the_api_uses() -> None:
    """API 用到的 6 个服务符号必须都在模块上且可调用（空壳类回归点）。"""
    service = api._get_job_service()
    for name in ("create_job", "list_jobs", "get_job", "get_job_detail", "arun_ocr", "delete_job"):
        assert callable(getattr(service, name)), f"job_service 缺少可调用的 {name}"


def test_list_jobs_passes_user_for_ownership_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    service = api._get_job_service()
    captured: dict[str, Any] = {}

    def _fake_list_jobs(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 0}

    monkeypatch.setattr(service, "list_jobs", _fake_list_jobs)
    request = _request()
    result = api.list_jobs(request, page=1, page_size=20)

    assert result["total"] == 0
    assert captured["user"] is request.user, "list_jobs 必须把当前用户传给服务层做属主收敛"
    assert captured["page"] == 1 and captured["page_size"] == 20


def test_get_job_endpoints_pass_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """按 job_id 操作任务的端点必须把 user 传下去（否则是 IDOR）。"""
    service = api._get_job_service()
    get_calls: list[tuple[str, Any]] = []
    delete_calls: list[tuple[str, Any]] = []

    request = _request()
    fake_job = SimpleNamespace(id="job-1", name="old", save=MagicMock())

    monkeypatch.setattr(service, "get_job", lambda job_id, user=None: (get_calls.append((job_id, user)), fake_job)[1])
    monkeypatch.setattr(service, "delete_job", lambda job_id, user=None: delete_calls.append((job_id, user)))
    monkeypatch.setattr(api, "_body", lambda request: {"name": "new"})

    api.update_job_name(request, "job-1")
    api.delete_job(request, "job-1")

    assert get_calls == [("job-1", request.user)], f"update_job_name 必须传 user，实际: {get_calls}"
    assert delete_calls == [("job-1", request.user)], f"delete_job 必须传 user，实际: {delete_calls}"


def test_actor_returns_none_for_anonymous() -> None:
    """未登录时传 None（服务层据此不做属主过滤，供内部/后台调用）。"""
    assert api._actor(_anonymous_request()) is None
    assert api._actor(_request()) is not None
