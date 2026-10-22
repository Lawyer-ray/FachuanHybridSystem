"""``apps.agent.pi.model_config`` 单元测试。

重点覆盖 ``reasoning`` 能力声明：pi 依赖 models.json 里的 ``reasoning: true``
才会启用 thinking 并把思考过程以 ``thinking_delta`` 推给前端。早期这里没有
该字段，导致后端即使开了思考模式，用户也看不到思考过程。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from apps.agent.pi import model_config


def _provider(**overrides: Any) -> SimpleNamespace:
    """构造一个足以渲染 models.json 的 provider 桩。"""

    class _P:
        name = "测试平台"
        base_url = "http://gw.example/v1"
        api_keys = "sk-test"  # pragma: allowlist secret
        default_model = "kimi-2.6"
        extra_models = ""
        enable_thinking = False

        def parsed_models(self) -> list[str]:
            return []

        def supports_thinking(self, model: str = "") -> bool:
            return "kimi" in (model or self.default_model).lower()

    p = _P()
    for key, value in overrides.items():
        setattr(p, key, value)
    return p  # type: ignore[return-value]


def _models_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload["providers"]["fachuan"]["models"]


class TestReasoningDeclaration:
    def test_reasoning_true_when_thinking_enabled(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(enable_thinking=True))
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["reasoning"] is True

    def test_reasoning_false_when_thinking_disabled(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(enable_thinking=False))
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["reasoning"] is False

    def test_non_reasoning_model_never_declares_reasoning(self, monkeypatch: Any) -> None:
        """普通模型即使平台开了思考开关，也不能声明 reasoning（会让 pi 发它不认的参数）。"""
        monkeypatch.setattr(
            model_config,
            "_load_provider",
            lambda hint="": _provider(default_model="glm53", enable_thinking=True),
        )
        payload = model_config.build_models_json("glm53")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["reasoning"] is False

    def test_entry_keeps_window_and_max_tokens(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(enable_thinking=True))
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["id"] == "kimi-2.6"
        assert entry["contextWindow"] == model_config.DEFAULT_CONTEXT_WINDOW
        assert entry["maxTokens"] == model_config.DEFAULT_MAX_TOKENS
