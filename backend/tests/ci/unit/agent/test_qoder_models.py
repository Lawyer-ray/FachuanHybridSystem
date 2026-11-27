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
def _clean_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """每条用例从干净缓存开始（模块级变量会跨用例留存）。

    **磁盘缓存也必须指到 tmp**：真机 `~/.fachuan-agent/qoder/models.json` 一旦存在，
    `list_models()` 会直接命中它、不再起子进程，用例就会变成「取决于我上次跑过什么」。
    """
    monkeypatch.setattr(qoder_models, "_cached_models", [])
    monkeypatch.setattr(qoder_models, "_cached_at", 0.0)
    monkeypatch.setattr(qoder_models, "_cached_failed_at", 0.0)
    monkeypatch.setattr(qoder_models, "_ttl", lambda: 600.0)
    monkeypatch.setattr("apps.agent.backends.qoder_accounts.qoder_home", lambda: tmp_path)
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


def test_disk_cache_lets_a_new_process_skip_the_subprocess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """落盘的意义：换进程（reload / 另一个 worker）不该再付一次 5 秒子进程。"""
    calls = _patch_run(monkeypatch, [["Auto", "fachuan-gw/kimi-2.6"]])
    assert qoder_models.list_models() == ["Auto", "fachuan-gw/kimi-2.6"]
    assert len(calls) == 1
    assert (tmp_path / qoder_models.CACHE_FILE_NAME).exists()

    # 模拟「新进程」：内存清空，磁盘还在
    monkeypatch.setattr(qoder_models, "_cached_models", [])
    monkeypatch.setattr(qoder_models, "_cached_at", 0.0)

    assert qoder_models.list_models() == ["Auto", "fachuan-gw/kimi-2.6"]
    assert len(calls) == 1, "磁盘命中后不该再起子进程"


def test_corrupt_disk_cache_is_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / qoder_models.CACHE_FILE_NAME).write_text("{半截 json", encoding="utf-8")
    calls = _patch_run(monkeypatch, [["Auto"]])

    assert qoder_models.list_models() == ["Auto"]
    assert len(calls) == 1


def test_default_model_prefers_the_firm_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """2026-11-27：不选模型时该跑律所的模型，不是 Qoder 云侧的 Auto。

    理由（见 `qoder_models.default_model` 的说明）：Auto 由 Qoder 账号套餐决定，
    本所账号实测报「You do not have access to this model service」；而
    `fachuan-gw/*` 走律所自己的网关，已经跑通。
    """
    _patch_run(monkeypatch, [["Auto", "Ultimate", "fachuan-gw/kimi-2.6", "fachuan-gw/glm53"]])

    assert qoder_models.default_model() == "fachuan-gw/kimi-2.6"
    # `/agent/backends` 报给前端的默认项必须与真正下发的一致
    assert qoder_models.for_display() == (
        ["Auto", "Ultimate", "fachuan-gw/kimi-2.6", "fachuan-gw/glm53"],
        "fachuan-gw/kimi-2.6",
    )


def test_default_model_falls_back_to_auto_without_firm_models(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, [["Auto", "Ultimate"]])
    assert qoder_models.default_model() == "Auto"


def test_cached_default_model_never_runs_the_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """发言路径的约束：拿默认模型不能等子进程。"""
    calls = _patch_run(monkeypatch, [["fachuan-gw/kimi-2.6"]])

    # 冷缓存：绝不触发子进程，返回 None（交给 CLI 默认）
    assert qoder_models.cached_default_model() is None
    assert len(calls) == 0

    # 缓存热了之后才给出律所模型
    assert qoder_models.list_models() == ["fachuan-gw/kimi-2.6"]
    assert qoder_models.cached_default_model() == "fachuan-gw/kimi-2.6"
    assert len(calls) == 1


def test_show_byok_off_hides_firm_models_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """关掉 BYOK 时不能让默认项还指向一个列不出来的模型。"""
    monkeypatch.setenv(qoder_models.SHOW_BYOK_ENV, "0")
    _patch_run(monkeypatch, [["Auto", "fachuan-gw/kimi-2.6"]])

    assert qoder_models.for_display() == (["Auto"], "Auto")


def test_parse_strips_display_name_even_when_the_id_has_parens() -> None:
    """BYOK 那一批的 id 本身可能带括号，不能因此把整行当 id 发给 CLI。"""
    output = "\n".join(
        [
            "model",
            "Auto",
            "kimi-2.6 (fachuan-gw/kimi-2.6)",
            "kimi-2.6(Anthropic) (fachuan-gw/kimi-2.6(Anthropic))",
            "",
        ]
    )

    assert qoder_models._parse(output) == [
        "Auto",
        "fachuan-gw/kimi-2.6",
        "fachuan-gw/kimi-2.6(Anthropic)",
    ]


def test_old_cache_format_is_discarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """解析规则改了就必须重跑：旧缓存里存的是「已解析的 id」，新代码没机会纠正。"""
    import json

    (tmp_path / qoder_models.CACHE_FILE_NAME).write_text(
        json.dumps({"models": ["显示名 (fachuan-gw/kimi-2.6)"], "at": 9e18}),  # 无版本号 = 旧格式
        encoding="utf-8",
    )
    calls = _patch_run(monkeypatch, [["fachuan-gw/kimi-2.6"]])

    assert qoder_models.list_models() == ["fachuan-gw/kimi-2.6"]
    assert len(calls) == 1
    payload = json.loads((tmp_path / qoder_models.CACHE_FILE_NAME).read_text(encoding="utf-8"))
    assert payload["v"] == qoder_models.CACHE_FORMAT
