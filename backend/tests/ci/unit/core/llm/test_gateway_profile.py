"""网关协议层（``apps/core/llm/gateway_profile.py``）的单元测试。

## 守的是什么

这一层把「网关认哪些字段 / 哪些档位 / 哪些模型能思考」从 5 处重复收敛成 1 处，
所以本文件逐条钉死它的对外口径：

1. **思考能力判定**：``kimi-k2`` 这类宽匹配模型必须判为可思考——服务通道原先只认
   ``kimi26``，于是同一模型在 copilot 里推理、在诉状生成里不推理，且没有任何报错；
2. **档位映射永不越界**：``medium`` 原样下发会 400（实测服务端原话见模块注释），
   所以 :func:`gateway_effort` 的返回值必须**永远** ∈ ``GATEWAY_EFFORTS``；
3. **下发字段的三行语义表**：``supported=False`` → 空 dict；``enabled=False`` →
   只发 ``thinking=false``、**不带** ``reasoning_effort``（实测省略开关 ≠ 关闭）；
4. **降级是否值得重试**：``400/401/422`` 换哪个模型都是同一个错，不能把降级链
   每个模型各打一遍（旧的 ``RETRYABLE_EXCEPTIONS`` 粗筛做不到这点）；
5. **降级链口径**：主模型在首位、``list[str]`` 与 DB 原串两种形态、去重保序。

本模块是纯函数模块（无 IO / DB / settings），因此全文件不需要 ``django_db``。
"""

from __future__ import annotations

import pytest

from apps.core.llm.exceptions import LLMAPIError, LLMAuthenticationError, LLMNetworkError, LLMTimeoutError
from apps.core.llm.gateway_profile import (
    DEFAULT_THINKING_LEVEL,
    GATEWAY_EFFORTS,
    RETRYABLE_EXCEPTIONS,
    ThinkingDirectives,
    fallback_chain,
    gateway_effort,
    is_retryable,
    model_supports_thinking,
    normalize_model_key,
    resolve_thinking,
    selectable_efforts,
    wire_fields,
)


class TestNormalizeModelKey:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("kimi-k2", "kimik2"),
            ("kimi26", "kimi26"),
            ("Kimi-2.6(Anthropic)", "kimi26anthropic"),
            ("deepseek_r1", "deepseekr1"),
            ("deepseek-r1", "deepseekr1"),
            ("glm-z", "glmz"),
            ("qwen3:32b", "qwen332b"),
            ("  MiMo / V1  ", "mimov1"),
            ("", ""),
        ],
    )
    def test_strips_separators_and_parentheses(self, raw: str, expected: str) -> None:
        assert normalize_model_key(raw) == expected


class TestModelSupportsThinking:
    @pytest.mark.parametrize(
        "model",
        [
            "kimi-k2",
            "kimi26",
            "kimi-2.6(Anthropic)",
            "deepseek-r1",
            "deepseek-reasoner",
            "glm-z",
            "qwq-32b",
            "mimo-v1",
        ],
    )
    def test_reasoning_models_are_supported(self, model: str) -> None:
        assert model_supports_thinking(model) is True

    @pytest.mark.parametrize("model", ["qwen3-235b", "gpt-4o", "glm53", ""])
    def test_unknown_models_are_not_supported(self, model: str) -> None:
        assert model_supports_thinking(model) is False

    def test_none_is_not_supported(self) -> None:
        assert model_supports_thinking(None) is False

    def test_kimi_k2_matches_wide_marker(self) -> None:
        """口径对齐的核心：``kimi-k2`` 曾因服务通道只认 ``kimi26`` 而漏判。"""
        assert model_supports_thinking("kimi-k2") is True


class TestGatewayEffort:
    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (None, DEFAULT_THINKING_LEVEL),
            ("", DEFAULT_THINKING_LEVEL),
            ("   ", DEFAULT_THINKING_LEVEL),
            ("off", "low"),
            ("OFF", "low"),
            ("minimal", "low"),
            ("low", "low"),
            ("medium", "high"),
            ("high", "high"),
            ("xhigh", "xhigh"),
            ("max", "max"),
            (" MAX ", "max"),
            ("bogus", DEFAULT_THINKING_LEVEL),
        ],
    )
    def test_maps_into_whitelist(self, level: str | None, expected: str) -> None:
        assert gateway_effort(level) == expected

    @pytest.mark.parametrize(
        "level",
        [None, "", "off", "minimal", "medium", "low", "high", "xhigh", "max", "bogus", "1", "100"],
    )
    def test_never_returns_value_outside_whitelist(self, level: str | None) -> None:
        assert gateway_effort(level) in GATEWAY_EFFORTS

    def test_medium_is_remapped_not_forwarded(self) -> None:
        """``medium`` 原样下发会 400，必须映射成 ``high``。"""
        assert gateway_effort("medium") == "high"
        assert gateway_effort("medium") != "medium"


class TestResolveThinking:
    """``supported`` × ``enabled`` 四种组合。"""

    def test_supported_and_switch_on(self) -> None:
        assert resolve_thinking("kimi-k2", enable_thinking=True) == ThinkingDirectives(
            supported=True, enabled=True, effort=DEFAULT_THINKING_LEVEL
        )

    def test_supported_and_switch_off(self) -> None:
        assert resolve_thinking("kimi-k2", enable_thinking=False) == ThinkingDirectives(
            supported=True, enabled=False, effort=DEFAULT_THINKING_LEVEL
        )

    def test_unsupported_and_switch_on(self) -> None:
        directives = resolve_thinking("qwen3-235b", enable_thinking=True)
        assert directives.supported is False
        assert directives.enabled is False

    def test_unsupported_and_switch_off(self) -> None:
        directives = resolve_thinking(None, enable_thinking=False)
        assert directives.supported is False
        assert directives.enabled is False

    @pytest.mark.parametrize("model", ["kimi-k2", "qwen3-235b", ""])
    @pytest.mark.parametrize("enable_thinking", [True, False])
    def test_effort_always_in_whitelist(self, model: str, enable_thinking: bool) -> None:
        assert resolve_thinking(model, enable_thinking=enable_thinking).effort in GATEWAY_EFFORTS


class TestResolveThinkingLevel:
    """``level`` 维度（契约 v2 新增）：``enabled`` 与档位是**与**关系，``effort`` 永不越界。"""

    @pytest.mark.parametrize("level", [None, "max", "off", "medium", "bogus"])
    @pytest.mark.parametrize("enable_thinking", [True, False])
    def test_effort_never_escapes_whitelist(self, level: str | None, enable_thinking: bool) -> None:
        directives = resolve_thinking("kimi-k2", enable_thinking=enable_thinking, level=level)
        assert directives.effort in GATEWAY_EFFORTS
        assert directives.enabled is (enable_thinking and level != "off")

    @pytest.mark.parametrize("enable_thinking", [True, False])
    def test_off_level_forces_disabled(self, enable_thinking: bool) -> None:
        """``level="off"`` 与平台总开关取与，任一为否则不思考；``effort`` 不能填 ``"off"``。"""
        directives = resolve_thinking("kimi-k2", enable_thinking=enable_thinking, level="off")
        assert directives.enabled is False
        assert directives.effort in GATEWAY_EFFORTS

    @pytest.mark.parametrize("level", [None, "max", "off", "medium", "bogus"])
    @pytest.mark.parametrize("enable_thinking", [True, False])
    def test_unsupported_model_stays_disabled(self, level: str | None, enable_thinking: bool) -> None:
        directives = resolve_thinking("qwen3-235b", enable_thinking=enable_thinking, level=level)
        assert directives.supported is False
        assert directives.enabled is False
        assert directives.effort in GATEWAY_EFFORTS

    @pytest.mark.parametrize(
        ("level", "expected"),
        [
            (None, DEFAULT_THINKING_LEVEL),
            ("max", "max"),
            ("medium", "high"),
            ("minimal", "low"),
            ("off", "low"),
            ("bogus", DEFAULT_THINKING_LEVEL),
        ],
    )
    def test_effort_follows_gateway_effort(self, level: str | None, expected: str) -> None:
        """档位→白名单的映射只此一处：``resolve_thinking`` 不得自己再算一遍。"""
        assert resolve_thinking("kimi-k2", enable_thinking=True, level=level).effort == expected

    def test_off_is_matched_case_insensitively(self) -> None:
        """与 :func:`gateway_effort` 共用归一化，避免「按 off 映射 effort 却判成开启」。"""
        assert resolve_thinking("kimi-k2", enable_thinking=True, level=" OFF ").enabled is False


class TestWireFields:
    """契约第 3 节的三行语义表，逐行断言。"""

    @pytest.mark.parametrize("enabled", [True, False])
    def test_unsupported_sends_nothing(self, enabled: bool) -> None:
        """模型没有这个开关时一个字段都不发（未知 ``chat_template_kwargs`` 会被当 400）。"""
        assert wire_fields(ThinkingDirectives(supported=False, enabled=enabled, effort="max")) == {}

    def test_enabled_sends_switch_and_effort(self) -> None:
        assert wire_fields(ThinkingDirectives(supported=True, enabled=True, effort="xhigh")) == {
            "chat_template_kwargs": {"thinking": True},
            "reasoning_effort": "xhigh",
        }

    def test_disabled_sends_explicit_false_without_effort(self) -> None:
        """关闭时必须显式发 ``false``（省略开关 ≠ 关闭），且**不带** ``reasoning_effort``。"""
        fields = wire_fields(ThinkingDirectives(supported=True, enabled=False, effort="max"))
        assert fields == {"chat_template_kwargs": {"thinking": False}}
        assert "reasoning_effort" not in fields

    def test_kimi_k2_end_to_end(self) -> None:
        """本次改造的用户可见结论：``kimi-k2`` 在任一通道都下发同一组字段。"""
        assert wire_fields(resolve_thinking("kimi-k2", enable_thinking=True)) == {
            "chat_template_kwargs": {"thinking": True},
            "reasoning_effort": DEFAULT_THINKING_LEVEL,
        }


class TestSelectableEfforts:
    def test_includes_off_before_whitelist(self) -> None:
        assert selectable_efforts() == ("off", "low", "high", "xhigh", "max")


class TestRetryableExceptions:
    def test_covers_timeout_network_and_api_errors(self) -> None:
        assert set(RETRYABLE_EXCEPTIONS) == {LLMTimeoutError, LLMNetworkError, LLMAPIError}

    def test_is_exception_tuple(self) -> None:
        """``except`` 语法要求元组里全是异常类（写成别的类型会 TypeError）。"""
        assert all(isinstance(exc, type) and issubclass(exc, BaseException) for exc in RETRYABLE_EXCEPTIONS)


class TestIsRetryable:
    """``RETRYABLE_EXCEPTIONS`` 只是粗筛，此处是精筛（契约 v2）：status_code 决定 4xx/5xx。"""

    @pytest.mark.parametrize("status_code", [500, 502, 503, 599])
    def test_server_errors_are_retryable(self, status_code: int) -> None:
        assert is_retryable(LLMAPIError(message="boom", status_code=status_code)) is True

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422, 429, 499])
    def test_client_errors_are_not_retryable(self, status_code: int) -> None:
        """一切 ``400 <= status < 500`` 换哪个模型都是同一个错。"""
        assert is_retryable(LLMAPIError(message="bad request", status_code=status_code)) is False

    def test_400_is_the_waste_this_fixes(self) -> None:
        """400 在粗筛 tuple 里，但降级重试它只会把链上每个模型各打一遍（4 倍计费）。"""
        error = LLMAPIError(message="reasoning_effort must be low/high/xhigh/max", status_code=400)
        assert isinstance(error, RETRYABLE_EXCEPTIONS) is True
        assert is_retryable(error) is False

    def test_statusless_api_error_is_retryable(self) -> None:
        """``_raise_mapped_error`` 最后那条兜底不带 status（非 HTTP 失败），按可重试处理。"""
        assert is_retryable(LLMAPIError(message="unclassified")) is True

    def test_timeout_and_network_are_retryable(self) -> None:
        assert is_retryable(LLMTimeoutError()) is True
        assert is_retryable(LLMNetworkError()) is True

    def test_other_exceptions_are_not_retryable(self) -> None:
        assert is_retryable(ValueError("nope")) is False

    def test_authentication_error_is_not_retryable(self) -> None:
        """401/403 走 ``LLMAuthenticationError``（非 ``LLMAPIError`` 子类），同样不该重试。"""
        assert is_retryable(LLMAuthenticationError()) is False


class TestFallbackChain:
    def test_mixed_separators(self) -> None:
        assert fallback_chain("kimi-2.6", "glm53; qwen3-235b\ndeepseek-v4, mimo-v1") == [
            "kimi-2.6",
            "glm53",
            "qwen3-235b",
            "deepseek-v4",
            "mimo-v1",
        ]

    def test_primary_stays_first_and_dedups(self) -> None:
        assert fallback_chain("kimi-2.6", "glm53, kimi-2.6, glm53, qwen3") == ["kimi-2.6", "glm53", "qwen3"]

    def test_empty_primary_returns_fallbacks_only(self) -> None:
        assert fallback_chain("", "glm53,, ;\n qwen3") == ["glm53", "qwen3"]
        assert fallback_chain(None, "glm53") == ["glm53"]

    def test_blank_entries_are_dropped(self) -> None:
        assert fallback_chain("  kimi-2.6  ", "  ,  ;  \n  ") == ["kimi-2.6"]

    def test_no_fallbacks(self) -> None:
        assert fallback_chain("kimi-2.6", None) == ["kimi-2.6"]
        assert fallback_chain(None, None) == []
        assert fallback_chain("", "") == []

    def test_accepts_service_channel_list(self) -> None:
        """服务通道 ``OpenAIProviderConfig.fallback_models`` 是 ``list[str]``（契约 v2）。"""
        assert fallback_chain("kimi-2.6", ["glm53", "qwen3-235b", "mimo-v1"]) == [
            "kimi-2.6",
            "glm53",
            "qwen3-235b",
            "mimo-v1",
        ]
        assert fallback_chain("kimi-2.6", ("glm53", "qwen3-235b")) == ["kimi-2.6", "glm53", "qwen3-235b"]

    def test_list_elements_use_the_same_cleaning_rules(self) -> None:
        """list 元素里也可能带逗号/分号/换行与前后空格（Admin 历史填报）。"""
        assert fallback_chain("kimi-2.6", [" glm53 , qwen3", "mimo-v1;", ""]) == [
            "kimi-2.6",
            "glm53",
            "qwen3",
            "mimo-v1",
        ]

    def test_list_form_dedups_and_keeps_primary_first(self) -> None:
        assert fallback_chain("kimi-2.6", ["glm53", "kimi-2.6", "glm53"]) == ["kimi-2.6", "glm53"]

    def test_list_form_with_empty_primary(self) -> None:
        assert fallback_chain("", ["glm53", "", " qwen3 "]) == ["glm53", "qwen3"]
        assert fallback_chain(None, []) == []
        assert fallback_chain("kimi-2.6", []) == ["kimi-2.6"]
