"""svg_fragment_generator_service.py 单元测试（LLM mock + bleach 消毒断言）.

覆盖白名单消毒（安全审计 XSS）、无 prompt / 解析失败 / 全非法片段的
回退路径，同步 generate 与异步 agenerate 双链路。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.story_viz.schemas import AnimationScript
from apps.story_viz.services.svg_fragment_generator_service import (
    SvgFragmentBundle,
    SvgFragmentGeneratorService,
    SvgFragmentItem,
    sanitize_svg_fragment,
)


def _script(prompts: list[str]) -> AnimationScript:
    return AnimationScript(title="t", viz_type="timeline", fragment_prompts=prompts)


def _bundle_response(items: list[SvgFragmentItem]) -> MagicMock:
    resp = MagicMock()
    resp.content = SvgFragmentBundle(fragments=items).model_dump_json()
    return resp


def _llm(resp: Any = None, exc: Exception | None = None) -> MagicMock:
    llm = MagicMock()
    if exc is not None:
        llm.chat = MagicMock(side_effect=exc)
        llm.achat = AsyncMock(side_effect=exc)
    else:
        llm.chat = MagicMock(return_value=resp)
        llm.achat = AsyncMock(return_value=resp)
    return llm


class TestSanitizeSvgFragment:
    def test_keeps_whitelisted_geometry(self) -> None:
        raw = "<g transform='translate(10)'><circle cx='1' cy='2' r='3' fill='red'/><text x='0' y='0'>标签</text></g>"
        cleaned = sanitize_svg_fragment(raw)
        assert "<circle" in cleaned
        assert "<text" in cleaned
        assert "translate(10)" in cleaned

    def test_strips_script_tag(self) -> None:
        cleaned = sanitize_svg_fragment("<circle r='1'/><script>alert(1)</script>")
        assert "script" not in cleaned.lower()
        assert "<circle" in cleaned

    def test_strips_event_handler_attributes(self) -> None:
        cleaned = sanitize_svg_fragment("<circle r='1' onload='alert(1)'/>")
        assert "onload" not in cleaned

    def test_strips_href_and_style(self) -> None:
        cleaned = sanitize_svg_fragment(
            "<g><a href='javascript:alert(1)'>x</a><path d='M0 0' style='position:fixed'/></g>"
        )
        assert "href" not in cleaned
        assert "javascript" not in cleaned
        assert "style=" not in cleaned
        assert "<path" in cleaned

    def test_strips_comments(self) -> None:
        cleaned = sanitize_svg_fragment("<!-- secret --><rect width='1' height='1'/>")
        assert "secret" not in cleaned


class TestGenerate:
    def test_no_prompts_returns_fallback(self) -> None:
        svc = SvgFragmentGeneratorService(llm_service=_llm())
        result = svc.generate(script=_script([]))
        assert [f["name"] for f in result["fragments"]] == ["pulse", "halo"]

    def test_success_sanitizes_and_keeps_valid(self) -> None:
        resp = _bundle_response(
            [
                SvgFragmentItem(name="ok", svg="<circle cx='0' cy='0' r='5' fill='blue'/>"),
                SvgFragmentItem(name="evil", svg="<script>alert(1)</script><circle r='1'/>"),
                SvgFragmentItem(name="plain_text", svg="no svg at all"),
            ]
        )
        svc = SvgFragmentGeneratorService(llm_service=_llm(resp), model="gpt-s")
        result = svc.generate(script=_script(["脉冲", "光环", "第三个被截断"]))

        # 只取前 3 个 prompt；纯文本片段被丢弃；script 标签被消毒
        assert [f["name"] for f in result["fragments"]] == ["ok", "evil"]
        assert "script" not in result["fragments"][1]["svg"].lower()
        # 模型与 temperature 透传
        call = svc._llm_service.chat.call_args
        assert call.kwargs["model"] == "gpt-s"
        assert call.kwargs["temperature"] == 0.0

    def test_only_first_three_prompts_sent(self) -> None:
        resp = _bundle_response([SvgFragmentItem(name="n", svg="<circle r='1'/>")])
        llm = _llm(resp)
        SvgFragmentGeneratorService(llm_service=llm).generate(script=_script(["a", "b", "c", "d", "e"]))
        user_content = llm.chat.call_args.kwargs["messages"][1]["content"]
        assert user_content.splitlines() == ["- a", "- b", "- c"]

    def test_all_invalid_fragments_return_fallback(self) -> None:
        resp = _bundle_response([SvgFragmentItem(name="x", svg="plain"), SvgFragmentItem(name="y", svg="<iframe/>")])
        svc = SvgFragmentGeneratorService(llm_service=_llm(resp))
        result = svc.generate(script=_script(["p"]))
        assert [f["name"] for f in result["fragments"]] == ["pulse", "halo"]

    def test_llm_exception_returns_fallback(self) -> None:
        svc = SvgFragmentGeneratorService(llm_service=_llm(exc=RuntimeError("llm down")))
        result = svc.generate(script=_script(["p"]))
        assert len(result["fragments"]) == 2

    def test_invalid_json_returns_fallback(self) -> None:
        resp = MagicMock()
        resp.content = "不是 JSON"
        svc = SvgFragmentGeneratorService(llm_service=_llm(resp))
        result = svc.generate(script=_script(["p"]))
        assert [f["name"] for f in result["fragments"]] == ["pulse", "halo"]


class TestAGenerate:
    @pytest.mark.asyncio
    async def test_async_no_prompts_fallback(self) -> None:
        svc = SvgFragmentGeneratorService(llm_service=_llm())
        result = await svc.agenerate(script=_script([]))
        assert len(result["fragments"]) == 2

    @pytest.mark.asyncio
    async def test_async_success(self) -> None:
        resp = _bundle_response([SvgFragmentItem(name="a", svg="<rect width='1' height='1'/>")])
        llm = _llm(resp)
        svc = SvgFragmentGeneratorService(llm_service=llm, model="m9")
        result = await svc.agenerate(script=_script(["p"]))
        assert result["fragments"][0]["name"] == "a"
        assert llm.achat.call_args.kwargs["model"] == "m9"

    @pytest.mark.asyncio
    async def test_async_exception_fallback(self) -> None:
        svc = SvgFragmentGeneratorService(llm_service=_llm(exc=RuntimeError("dead")))
        result = await svc.agenerate(script=_script(["p"]))
        assert [f["name"] for f in result["fragments"]] == ["pulse", "halo"]

    @pytest.mark.asyncio
    async def test_async_all_invalid_fallback(self) -> None:
        resp = _bundle_response([SvgFragmentItem(name="x", svg="plain text")])
        svc = SvgFragmentGeneratorService(llm_service=_llm(resp))
        result = await svc.agenerate(script=_script(["p"]))
        assert [f["name"] for f in result["fragments"]] == ["pulse", "halo"]


class TestFallbackShape:
    def test_fallback_fragments_are_valid_svg(self) -> None:
        svc = SvgFragmentGeneratorService(llm_service=_llm())
        result = svc.generate(script=_script([]))
        for frag in result["fragments"]:
            assert frag["svg"].startswith("<circle")
            # 回退片段自身在白名单内（消毒后仍保留 circle 标签）
            assert "<circle" in sanitize_svg_fragment(frag["svg"])
