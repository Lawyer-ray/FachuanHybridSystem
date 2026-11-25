"""``disagreement_judge``（多引擎分歧的第三方打分裁定器）的判据单测。

全部请求都被 ``httpx.MockTransport`` 截获，**一个字节都不出网**；退避睡眠也打成 no-op，
否则 429 / 网络异常类用例要真等 3.5s。

用例围绕实现里那四条实测约束组织：

1. 并发 > 2 就 429 → 429 两次后重试成功，且**不**再多试。
2. 真实证件图必被 ``content_policy_violation`` 拒 → 不重试、整次判定交人工、只发一次请求。
3. ``prob_yes`` 绝对值不可作阈值 → 只测「胜者/次高分」比率与胜者分下限两条判据。
4. 错值也能拿 0.58 → 比率不够就交人工（``ratio_low``）。

候选文本一律用虚构/脱敏数据（``张三丰`` / ``张四丰`` / ``ABCDEFGH…``），真实卷宗里的
姓名、证件号、金额不得出现在测试里。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

import httpx
import pytest

from apps.pdf_splitting.services.split import disagreement_judge as judge

#: 不是真图：本文件所有请求都由 MockTransport 应答，字节内容不参与任何判定。
_IMAGE_BYTES = b"fake-png-bytes-for-mocktransport"

_Handler = Callable[[httpx.Request], httpx.Response]


class _RecordingLogger:
    """替身 logger：记录 ``(event, extra)``，用于断言「日志里不许出现候选原文」。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, *, extra: dict[str, Any]) -> None:
        self.records.append((event, extra))

    def warning(self, event: str, *, extra: dict[str, Any]) -> None:
        self.records.append((event, extra))

    def rendered(self) -> str:
        return repr(self.records)


@pytest.fixture(autouse=True)
def _clean_snapshots() -> Iterator[None]:
    """``_SNAPSHOTS`` 是模块级环形缓冲：用例之间必须清空，否则 snapshot 断言互相污染。"""
    judge._SNAPSHOTS.clear()
    yield
    judge._SNAPSHOTS.clear()


def _settings(**overrides: Any) -> judge._Settings:
    """一份「已启用、参数即默认值」的配置快照（用例只改自己关心的那几项）。"""
    base = judge._Settings(
        enabled=True,
        api_key="test-key",  # pragma: allowlist secret —— 假 key，MockTransport 不会发出去
    )
    return replace(base, **overrides)


def _scored_body(prob_yes: float) -> bytes:
    """打分成功响应：``choices[0].message.content`` 是 **JSON 字符串**（实测口径）。"""
    content = json.dumps({"results": [{"verdict": "scored", "prob_yes": prob_yes, "detail": ""}]})
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 512, "completion_tokens": 0},
    }
    return json.dumps(body).encode()


def _policy_body() -> bytes:
    return json.dumps({"error": {"code": "content_policy_violation", "message": "rejected"}}).encode()


def _rate_limited_body() -> bytes:
    return json.dumps({"error": {"code": "rate_limit_exceeded", "message": "too many"}}).encode()


def _text_of(request: httpx.Request) -> str:
    """取请求体里那条候选文本（用它做分派，才能断言「哪一条被请求了几次」）。"""
    payload = json.loads(request.content.decode("utf-8"))
    return str(payload["messages"][0]["content"][1]["text"])


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler: _Handler) -> list[httpx.Request]:
    """把 ``_build_client`` 换成 MockTransport 客户端，返回实际发出的请求列表。

    同时把 ``_sleep_before_retry`` 打成 no-op：退避睡眠本身不是本文件的被测对象，
    真睡会让每个重试用例固定多等 0.5–3.5s。
    """
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    def _client(_settings: judge._Settings) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(_record), timeout=5.0, trust_env=False)

    monkeypatch.setattr(judge, "_build_client", _client)
    monkeypatch.setattr(judge, "_sleep_before_retry", lambda *, attempt, slept_seconds: slept_seconds)
    return seen


def _forbidden(_request: httpx.Request) -> httpx.Response:
    """本路径**一次请求都不许发**：被调用即用例失败。"""
    raise AssertionError("本路径不应发出任何 HTTP 请求")


def _plan_handler(plan: dict[str, list[tuple[int, bytes]]]) -> _Handler:
    """按候选文本分派响应：每条文本一个队列，用完后一直重复最后一个响应。"""

    def _handler(request: httpx.Request) -> httpx.Response:
        queue = plan[_text_of(request)]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(status, content=body)

    return _handler


def _calls_for(seen: list[httpx.Request], text: str) -> int:
    return sum(1 for request in seen if _text_of(request) == text)


# ── 配置 ────────────────────────────────────────────────────────────────


def test_default_config_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """库里没有这两个键时：默认**关闭**、key 为空。"""
    monkeypatch.setattr(judge.SystemConfigService, "get_value", lambda self, key, default="": default)

    settings = judge._load_settings()

    assert settings.enabled is False, 'OCR_JUDGE_ENABLED 默认 "0"：不配就是关'
    assert settings.api_key == ""


def test_only_two_keys_live_in_system_config() -> None:
    """棘轮：**只有开关与 key** 允许进配置表。

    其余六项（接口地址 / 模型名 / 并发上限 / 超时 / 比率下限 / 分数下限）都是实测出来的
    工程常数，写进 admin 只会给「随手调松阈值」开门，而调松是静默生效的——不会报错，
    只会悄悄把更多错值采信成对的。要改这些数，请改代码并带上实测依据。
    """
    assert set(judge._CONFIG_DEFAULTS) == {judge.OCR_JUDGE_ENABLED_KEY, judge.OCR_JUDGE_API_KEY_KEY}
    # 六个常量的类型与量级也要在（防止有人把它们挪走时顺手改坏）
    assert judge.JUDGE_API_URL.startswith("https://")
    assert judge.JUDGE_MODEL == "MiniCPM-OCR-Jev"
    assert judge.JUDGE_MAX_CONCURRENCY == judge._HARD_CONCURRENCY_CAP == 2
    assert judge.JUDGE_TIMEOUT_SECONDS >= 60
    assert judge.JUDGE_RATIO_MIN >= 2
    assert 0 < judge.JUDGE_PROB_FLOOR < 1


def test_disabled_judgement_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """规则 1：未启用 → human/disabled，不构造客户端、不打分。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings(enabled=False))
    seen = _install_transport(monkeypatch, _forbidden)

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.reason, judgement.winner) == (
        judge.DECISION_HUMAN,
        judge.REASON_DISABLED,
        None,
    )
    assert judgement.scores == ()
    assert seen == []


# ── 规则 2：证件/账号类字段一次 HTTP 都不发 ─────────────────────────────────


@pytest.mark.parametrize("domain", sorted(judge.BLOCKED_DOMAINS))
def test_blocked_domain_never_sends_request(monkeypatch: pytest.MonkeyPatch, domain: str) -> None:
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(monkeypatch, _forbidden)

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"], domain=domain)

    assert (judgement.decision, judgement.reason) == (judge.DECISION_HUMAN, judge.REASON_DOMAIN_BLOCKED)
    assert judgement.scores == ()
    assert seen == [], "证件/账号类字段必被 content_policy_violation 拒，不该白发一次请求"


# ── 规则 3：去重后只剩一条 ───────────────────────────────────────────────────


def test_identical_candidates_accepted_without_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """去重后只剩一条（含空白候选被丢弃）→ accept/identical，零请求。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(monkeypatch, _forbidden)

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张三丰", "  ", "张三丰"])

    assert (judgement.decision, judgement.winner, judgement.reason) == (
        judge.DECISION_ACCEPT,
        "张三丰",
        judge.REASON_IDENTICAL,
    )
    assert judgement.scores == ()
    assert seen == []


# ── 规则 4：策略拒绝不可重试，且只发一次请求 ────────────────────────────────


def test_policy_rejection_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(400, _policy_body())],
                "张四丰": [(200, _scored_body(0.99))],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.reason, judgement.winner) == (
        judge.DECISION_HUMAN,
        judge.REASON_POLICY_REJECTED,
        None,
    )
    assert len(seen) == 1, "策略拒绝重试必然还拒；结论已定，不再为剩余候选发请求"
    assert judgement.scores == (
        judge.CandidateScore(
            text="张三丰",
            prob_yes=None,
            verdict=judge.VERDICT_POLICY_REJECTED,
            detail="content_policy_violation",
        ),
    )
    assert judgement.ratio is None, "没算过比率就不该编一个出来"


# ── 规则 5：调用失败（401 不重试 / 网络异常退避耗尽）─────────────────────────


def test_unauthorized_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """401/403 换不来新结果（key 不会自己变好）→ 每条候选只请求一次。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(401, b'{"error": "invalid_api_key"}')],
                "张四丰": [(403, b'{"error": "forbidden"}')],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.reason) == (judge.DECISION_HUMAN, judge.REASON_CALL_FAILED)
    assert len(seen) == 2
    assert [score.detail for score in judgement.scores] == ["http_401", "http_403"]


def test_transport_error_fails_open_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """网络异常：退避重试到上限后 fail-open 成 human/call_failed，异常不穿透。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("upstream unreachable", request=request)

    seen = _install_transport(monkeypatch, _handler)

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.reason) == (judge.DECISION_HUMAN, judge.REASON_CALL_FAILED)
    assert len(seen) == 2 * judge._MAX_ATTEMPTS, "每条候选最多 4 次尝试（首次 + 3 次重试）"
    assert {score.verdict for score in judgement.scores} == {judge.VERDICT_FAILED}
    assert judgement.scores[0].detail == "transport:ConnectError"


def test_policy_rejection_outranks_call_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """规则 4 优先于规则 5：失败不短路，后面的策略拒绝仍要被发现（结论同为交人工，reason 不同）。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(401, b'{"error": "invalid_api_key"}')],
                "张四丰": [(400, _policy_body())],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert judgement.reason == judge.REASON_POLICY_REJECTED
    assert len(seen) == 2


# ── 429 退避重试 ────────────────────────────────────────────────────────────


def test_rate_limit_retries_two_times_then_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 两次后成功：第 3 次就拿到分，不该再多试。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(429, _rate_limited_body()), (429, _rate_limited_body()), (200, _scored_body(0.99))],
                "张四丰": [(200, _scored_body(0.01))],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert _calls_for(seen, "张三丰") == 3
    assert (judgement.decision, judgement.winner, judgement.reason) == (
        judge.DECISION_ACCEPT,
        "张三丰",
        judge.REASON_RATIO_OK,
    )


def test_rate_limit_retries_are_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """一直 429 → 尝试次数封顶（首次 + 3 次重试），不会无限重试。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(429, _rate_limited_body())],
                "张四丰": [(429, _rate_limited_body())],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert _calls_for(seen, "张三丰") == judge._MAX_ATTEMPTS
    assert judgement.reason == judge.REASON_CALL_FAILED
    assert judgement.scores[0].detail == "http_429"


# ── 规则 7–9：相对比较 ──────────────────────────────────────────────────────


def test_prob_low_when_best_below_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    """比率很大但两边分都极低 → prob_low（「两个都不像」里挑一个不算采信）。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(200, _scored_body(0.04))],
                "张四丰": [(200, _scored_body(0.001))],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.reason, judgement.winner) == (
        judge.DECISION_HUMAN,
        judge.REASON_PROB_LOW,
        None,
    )
    assert judgement.ratio == pytest.approx(40.0)


def test_ratio_low_when_scores_are_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """实测错值也能拿 0.58：0.996 vs 0.158 只差 6.3 倍 → 拉不开，交人工。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(200, _scored_body(0.996))],
                "张四丰": [(200, _scored_body(0.158))],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.reason, judgement.winner) == (
        judge.DECISION_HUMAN,
        judge.REASON_RATIO_LOW,
        None,
    )
    assert judgement.ratio == pytest.approx(0.996 / 0.158)


def test_ratio_ok_accepts_winner_despite_low_absolute_prob(monkeypatch: pytest.MonkeyPatch) -> None:
    """真值绝对分只有 0.158 也能采信——只要它比次高分拉开 ≥ ratio_min 倍且高于下限。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(200, _scored_body(0.158))],
                "张四丰": [(200, _scored_body(0.01))],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.winner, judgement.reason) == (
        judge.DECISION_ACCEPT,
        "张三丰",
        judge.REASON_RATIO_OK,
    )
    assert judgement.ratio == pytest.approx(15.8)
    assert judgement.scores[0].prob_yes == pytest.approx(0.158)


def test_ratio_uses_epsilon_when_runner_up_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """次高分恰为 0 时比率用 1e-9 兜底（不开除零、也不把比率压成 1）。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰": [(200, _scored_body(0.9))],
                "张四丰": [(200, _scored_body(0.0))],
            }
        ),
    )

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert judgement.decision == judge.DECISION_ACCEPT
    assert judgement.ratio == pytest.approx(0.9 / 1e-9)


# ── 留痕：日志与快照都只留掩码文本 ────────────────────────────────────


def test_mask_keeps_head_and_length_for_long_text() -> None:
    assert judge._mask("ABCDEFGHIJKLMNOPQRST") == "ABCDEFGH…len=20"


def test_mask_hides_short_text_entirely() -> None:
    """不超过 8 个字符的候选往往就是姓名本身：一个字符都不给，只留长度。"""
    masked = judge._mask("张三丰")

    assert masked == "len=3"
    assert "张三丰" not in masked


def test_log_never_contains_full_candidate_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """日志字段齐全，但候选原文一个字都不许出现。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    _install_transport(
        monkeypatch,
        _plan_handler(
            {
                "张三丰向李四借款": [(200, _scored_body(0.99))],
                "张三丰向王五借款": [(200, _scored_body(0.01))],
            }
        ),
    )
    logger = _RecordingLogger()
    monkeypatch.setattr(judge, "logger", logger)

    judge.judge_candidates(_IMAGE_BYTES, ["张三丰向李四借款", "张三丰向王五借款"])

    event, extra = logger.records[-1]
    assert event == "ocr_disagreement_judge_done"
    assert set(extra) == {
        "domain",
        "decision",
        "reason",
        "ratio",
        "latency_ms",
        "tokens",
        "prompt_tokens",
        "scores",
    }
    assert extra["decision"] == judge.DECISION_ACCEPT
    assert extra["reason"] == judge.REASON_RATIO_OK
    assert extra["scores"] == [
        {"text": "len=8", "verdict": judge.VERDICT_SCORED, "prob_yes": 0.99},
        {"text": "len=8", "verdict": judge.VERDICT_SCORED, "prob_yes": 0.01},
    ]
    assert extra["prompt_tokens"] == 1024, "两次请求各 512 prompt tokens"
    assert extra["tokens"] == 0, "实测 completion_tokens 恒为 0"
    rendered = logger.rendered()
    assert "张三丰" not in rendered
    assert "李四" not in rendered
    assert "王五" not in rendered


def test_snapshot_caps_entries_and_only_keeps_masked_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """环形缓冲只留最近 N 条，且只有掩码文本。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())
    seen = _install_transport(monkeypatch, _forbidden)

    for _ in range(judge._SNAPSHOT_MAX + 7):
        judge.judge_candidates(_IMAGE_BYTES, ["张三丰向李四借款"])

    entries = judge.snapshot()

    assert len(entries) == judge._SNAPSHOT_MAX
    assert entries[-1]["decision"] == judge.DECISION_ACCEPT
    assert entries[-1]["reason"] == judge.REASON_IDENTICAL
    assert entries[-1]["scores"] == []
    assert "张三丰" not in repr(entries)
    assert judge.snapshot(3) == entries[-3:]
    assert judge.snapshot(0) == []
    assert seen == []


# ── fail-open 兜底 ──────────────────────────────────────────────────────────


def test_unexpected_error_falls_open_to_call_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """链路上任何意外（这里用编码图失败模拟）都落 human/call_failed，绝不穿透。"""
    monkeypatch.setattr(judge, "_load_settings", lambda: _settings())

    def _boom(_image_bytes: bytes) -> str:
        raise TypeError("boom")

    monkeypatch.setattr(judge, "_data_url", _boom)
    logger = _RecordingLogger()
    monkeypatch.setattr(judge, "logger", logger)

    judgement = judge.judge_candidates(_IMAGE_BYTES, ["张三丰", "张四丰"])

    assert (judgement.decision, judgement.reason) == (judge.DECISION_HUMAN, judge.REASON_CALL_FAILED)
    assert [event for event, _extra in logger.records] == [
        "ocr_disagreement_judge_unexpected_error",
        "ocr_disagreement_judge_done",
    ]
