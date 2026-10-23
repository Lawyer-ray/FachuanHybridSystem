"""``apps.agent.pi.model_config`` 单元测试。

重点覆盖面：

- ``reasoning`` 能力声明：pi 依赖 models.json 里的 ``reasoning: true`` 才会启用
  thinking 并把思考过程以 ``thinking_delta`` 推给前端。早期这里没有该字段，
  导致后端即使开了思考模式，用户也看不到思考过程。
- ``input`` 视觉声明：pi 只在 ``model.input`` 含 ``"image"`` 时才下发 image_url，
  缺声明则图片被静默降级成 "(see attached image)" 文本。
- ``settings.json`` 的 ``images.blockImages`` 闸门：防止用户级配置把图块静默吞掉。
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
        vision_model = ""
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


class TestVisionInputDeclaration:
    """``input`` 声明是 pi 的 vision gate。

    pi 的 openai-completions 适配器只在 ``model.input`` 含 ``"image"`` 时
    才把 image block 转成 ``image_url``；缺该字段时 pi 默认 ``["text"]``，
    用户上传的图被静默降级为 "(see attached image)" 文本——不报错、无日志。
    真值来源是已有的 ``provider.vision_model``（语义为「该平台的多模态模型名」）。
    """

    def test_default_provider_has_no_image_input(self, monkeypatch: Any) -> None:
        """``vision_model`` 空（默认）→ 只有 text，不能给纯文本模型错报 vision。"""
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider())
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["input"] == ["text"]

    def test_exact_vision_model_gets_image_input(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(vision_model="kimi-2.6"))
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["input"] == ["text", "image"]

    def test_matching_ignores_case_and_surrounding_whitespace(self, monkeypatch: Any) -> None:
        """vision_model 大小写/首尾空白差异仍应命中（配置常见录入差异，不是能力差异）。"""
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(vision_model="  Kimi-2.6  "))
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["input"] == ["text", "image"]

    def test_other_model_declared_as_vision_keeps_text_only(self, monkeypatch: Any) -> None:
        """vision_model 是别的模型 → 当前模型仍只有 text。

        匹配必须精确相等：前缀/子串匹配会把视觉能力误传给纯文本模型，
        网关收到它不认的 ``image_url`` 会直接 400。
        """
        monkeypatch.setattr(
            model_config,
            "_load_provider",
            lambda hint="": _provider(vision_model="qwen-vl-max", extra_models="kimi-2.6,glm53"),
        )
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        by_id = {entry["id"]: entry for entry in _models_of(payload)}
        assert by_id["kimi-2.6"]["input"] == ["text"]
        assert by_id["glm53"]["input"] == ["text"]

    def test_prefix_of_vision_model_is_not_vision(self, monkeypatch: Any) -> None:
        """反向覆盖：模型名只是 vision_model 的前缀也不算命中（禁止前缀匹配）。"""
        monkeypatch.setattr(
            model_config,
            "_load_provider",
            lambda hint="": _provider(vision_model="kimi-2.6-vision"),
        )
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        by_id = {entry["id"]: entry for entry in _models_of(payload)}
        assert by_id["kimi-2.6"]["input"] == ["text"]

    def test_gateway_branch_declares_image_input_for_vision_model(self, monkeypatch: Any) -> None:
        """网关分支与非网关分支共用 ``_model_entry``，两条分支都要声明 input。"""
        monkeypatch.setenv(model_config.GATEWAY_URL_ENV, "http://gw.example/v1")
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(vision_model="kimi-2.6"))
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        provider_cfg = payload["providers"]["fachuan"]
        assert provider_cfg["baseUrl"] == "http://gw.example/v1"
        by_id = {entry["id"]: entry for entry in provider_cfg["models"]}
        assert by_id["kimi-2.6"]["input"] == ["text", "image"]

    def test_gateway_branch_keeps_text_only_without_vision_model(self, monkeypatch: Any) -> None:
        monkeypatch.setenv(model_config.GATEWAY_URL_ENV, "http://gw.example/v1")
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider())
        payload = model_config.build_models_json("kimi-2.6")
        assert payload is not None
        [entry] = _models_of(payload)
        assert entry["input"] == ["text"]


class TestSupportsImageInput:
    """``supports_image_input`` 供下游决定走视觉路径还是 OCR 文本路径。"""

    def test_true_when_model_is_vision_model(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(vision_model="kimi-2.6"))
        assert model_config.supports_image_input("kimi-2.6") is True

    def test_false_when_model_is_text_only(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider())
        assert model_config.supports_image_input("kimi-2.6") is False

    def test_false_when_vision_model_is_another_model(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(vision_model="qwen-vl-max"))
        assert model_config.supports_image_input("kimi-2.6") is False

    def test_false_when_no_provider(self, monkeypatch: Any) -> None:
        """无 provider 时 fail-closed：不发网关不认的 image_url。"""
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": None)
        assert model_config.supports_image_input("kimi-2.6") is False

    def test_defaults_to_provider_default_model(self, monkeypatch: Any) -> None:
        """model_hint 为空时回落 default_model，与 models.json 实际渲染的模型保持一致。"""
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(vision_model="kimi-2.6"))
        assert model_config.supports_image_input() is True


class TestSettingsJson:
    """隔离目录的 settings.json：pin provider/model + 写思考等级。

    pi 的思考开关是 settings.json 的 modelThinkingLevels（参数为
    ``<provider>/<modelId>``），不是 models.json 的 reasoning 字段。
    """

    def test_writes_thinking_level_when_enabled(self, monkeypatch: Any, tmp_path: Any) -> None:
        import json as _json

        from apps.agent.pi import shared_mcp

        monkeypatch.setattr(
            shared_mcp, "_load_provider", lambda hint="": _provider(enable_thinking=True), raising=False
        )
        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(enable_thinking=True))
        path = shared_mcp._write_settings_json(tmp_path, model_hint="kimi-2.6")
        assert path is not None
        data = _json.loads(path.read_text(encoding="utf-8"))
        assert data["defaultProvider"] == "fachuan"
        assert data["defaultModel"] == "kimi-2.6"
        assert data["modelThinkingLevels"] == {"fachuan/kimi-2.6": "medium"}

    def test_no_thinking_level_when_disabled(self, monkeypatch: Any, tmp_path: Any) -> None:
        import json as _json

        from apps.agent.pi import shared_mcp

        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(enable_thinking=False))
        path = shared_mcp._write_settings_json(tmp_path, model_hint="kimi-2.6")
        assert path is not None
        data = _json.loads(path.read_text(encoding="utf-8"))
        assert "modelThinkingLevels" not in data
        # provider/model 仍要 pin，否则用户级 settings 会盖掉我们的 models.json
        assert data["defaultProvider"] == "fachuan"

    def test_returns_none_without_provider(self, monkeypatch: Any, tmp_path: Any) -> None:
        from apps.agent.pi import shared_mcp

        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": None)
        assert shared_mcp._write_settings_json(tmp_path, model_hint="kimi-2.6") is None

    def test_unblocks_images_in_isolated_settings(self, monkeypatch: Any, tmp_path: Any) -> None:
        """``images.blockImages`` 必须显式为 False。

        pi 默认该值为 false，但用户级 ``~/.pi/agent/settings.json`` 若被改成 true，
        会把 image block 整块换成 "Image reading is disabled." 且不报错——
        隔离目录不显式盖掉，models.json 里的 ``input: ["text", "image"]`` 被静默作废。
        """
        import json as _json

        from apps.agent.pi import shared_mcp

        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider())
        path = shared_mcp._write_settings_json(tmp_path, model_hint="kimi-2.6")
        assert path is not None
        data = _json.loads(path.read_text(encoding="utf-8"))
        assert data["images"]["blockImages"] is False

    def test_images_gate_written_even_when_thinking_disabled(self, monkeypatch: Any, tmp_path: Any) -> None:
        """images 闸门与思考开关无关，两条分支都必须写（不能只在有 level 时写）。"""
        import json as _json

        from apps.agent.pi import shared_mcp

        monkeypatch.setattr(model_config, "_load_provider", lambda hint="": _provider(enable_thinking=False))
        path = shared_mcp._write_settings_json(tmp_path, model_hint="kimi-2.6")
        assert path is not None
        data = _json.loads(path.read_text(encoding="utf-8"))
        assert "modelThinkingLevels" not in data
        assert data["images"]["blockImages"] is False
