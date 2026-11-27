"""qoder 模型清单的缓存口径（全离线：``_run`` 与配置目录都替身，不起子进程、不联网）。

守的是 2026-11-27 的那次现场：``--list-models`` 持续失败时，`GET /agent/backends`
每次都重跑子进程直到超时（实测端点被拖到 **15 秒**），而前端在首屏就打开切换器，
看到的是「后端清单暂不可用」——一个可以自愈的慢请求被显示成了功能坏掉。

所以这里只钉两件事：
1. **成功进缓存**：TTL 内不再起子进程；
2. **失败也进缓存**（``FAILURE_TTL_SECONDS``）：窗口内不再起子进程，窗口外才重试；
   而 ``invalidate()``（登录成功时调）要把失败窗口一起清掉——刚登录就要能立刻重试。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.agent.backends import qoder_models


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """每条用例从干净缓存开始（模块级变量会跨用例留存）。"""
    monkeypatch.setattr(qoder_models, "_cached_models", [])
    monkeypatch.setattr(qoder_models, "_cached_at", 0.0)
    monkeypatch.setattr(qoder_models, "_cached_failed_at", 0.0)
    monkeypatch.setattr(qoder_models, "_ttl", lambda: 600.0)
    # 配置目录存在（= 有账号可问），这样失败来自 _run 而不是「没有账号」
    monkeypatch.setattr("apps.agent.backends.qoder_accounts.any_config_dir", lambda: Path("/tmp/qoder-test"))


def _patch_run(monkeypatch: pytest.MonkeyPatch, results: list[list[str]]) -> list[int]:
    """按调用顺序返回 results 里的结果，并记下子进程被起了几次。"""
    calls: list[int] = []

    def _fake_run(_config_dir: Path) -> list[str]:
        calls.append(1)
        return results[min(len(calls), len(results)) - 1]

    monkeypatch.setattr(qoder_models, "_run", _fake_run)
    return calls


def test_success_is_cached_within_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_run(monkeypatch, [["Auto", "Ultimate"]])

    assert qoder_models.list_models() == ["Auto", "Ultimate"]
    assert qoder_models.list_models() == ["Auto", "Ultimate"]

    assert len(calls) == 1, "TTL 内不该再起子进程"


def test_failure_is_not_retried_within_failure_window(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_run(monkeypatch, [[]])

    assert qoder_models.list_models() == []
    assert qoder_models.list_models() == []

    assert len(calls) == 1, "刚失败过就重跑子进程，正是把端点拖到 15 秒的那条路"


def test_failure_window_expires_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_run(monkeypatch, [[], ["Auto"]])
    qoder_models.list_models()
    assert len(calls) == 1

    # 把失败时刻挪到窗口之外（不 sleep，直接改时间戳）
    monkeypatch.setattr(qoder_models, "_cached_failed_at", 1.0)

    assert qoder_models.list_models() == ["Auto"]
    assert len(calls) == 2


def test_previous_list_survives_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """短暂失败不该让已经拿到的清单消失（下拉里的模型会突然「没了」）。"""
    _patch_run(monkeypatch, [["Auto", "Ultimate"], []])
    assert qoder_models.list_models() == ["Auto", "Ultimate"]

    # 让成功缓存过期，但失败窗口内仍有上次结果可用
    monkeypatch.setattr(qoder_models, "_cached_at", 0.0)
    monkeypatch.setattr(qoder_models, "_cached_failed_at", 0.0)

    assert qoder_models.list_models() == ["Auto", "Ultimate"]


def test_invalidate_clears_failure_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """登录成功后要能立刻重试：失败窗口不清就等于「刚登录还得再等一分钟」。"""
    calls = _patch_run(monkeypatch, [[], ["Auto"]])
    qoder_models.list_models()
    assert len(calls) == 1

    qoder_models.invalidate()

    assert qoder_models.list_models() == ["Auto"]
    assert len(calls) == 2
