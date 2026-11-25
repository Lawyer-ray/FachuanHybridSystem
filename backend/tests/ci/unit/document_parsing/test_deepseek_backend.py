"""DeepSeek OCR 后端：产物流形、退化页修补、凭证来源、注册与可用性判据。

真打云端的那部分不在这里（CI 没 Key）。这里锁的是**契约**：

- 页号必须 1 起、`layout["pages"][i]` 必须有 `text`——`ocr_handler.parse_cloud_pages`
  认不出页就会整份报「no page-indexed results」；
- 退化页必须换 purpose 单页重试，且**修好的页要替换正文**；
- 整页只有一张图时必须判退化（否则那页的正文就是一句坐标串）；
- 可用性只看 SystemConfig 有没有 Key（它没有 `DocumentParseProvider` 行）。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from apps.document_parsing.services.backends.deepseek_backend import DeepSeekOCRBackend, _parse_rich_blocks

#: rich 模式的真实返回形态（照 2026-11-25 实测逐字抄）：分隔符是全角竖线 U+FF5C，
#: 块类型词夹在 `ref` 与 `/ref` **之间**，坐标在 `box` 那一对标签里。
_RICH_PAGE = (
    "<\uff5cref\uff5c>title<\uff5c/ref\uff5c><\uff5cbox\uff5c>[[586,323,704,677]]<\uff5c/box\uff5c>"
    " 授权委托书\n"
    "<\uff5cref\uff5c>text<\uff5c/ref\uff5c><\uff5cbox\uff5c>[[100,100,900,160]]<\uff5c/box\uff5c>"
    " 委托人：某某公司"
)
#: 整页就是一张图的形态（rich 模式对「照片页」的如实自述）。
_IMAGE_ONLY = "<\uff5cref\uff5c>image<\uff5c/ref\uff5c><\uff5cbox\uff5c>[[0,0,999,999]]<\uff5c/box\uff5c>"


def _payload(pages: list[tuple[int, str, str]], usage: dict | None = None) -> dict[str, Any]:
    return {
        "page_count": len(pages),
        "pages": [{"index": index, "text": text, "finish_reason": finish} for index, text, finish in pages],
        "usage": usage or {"total_tokens": 100},
    }


class _StubBackend(DeepSeekOCRBackend):
    """把 HTTP 换成一个可编程的桩：按调用顺序吐出预设 payload。"""

    def __init__(self, responses: list[dict[str, Any]], **kwargs: Any) -> None:
        # 显式给齐 purpose / api_url：否则属性会去读 SystemConfig（要 DB），
        # 本文件的用例刻意不碰数据库。
        options: dict[str, Any] = {
            "api_key": "test-key",  # pragma: allowlist secret（桩用的假 Key）
            "purpose": "text_recognition",
            "api_url": "https://example.invalid/v1/tools/ocr",
        }
        options.update(kwargs)
        super().__init__(**options)
        self._responses = list(responses)
        self.calls: list[str] = []

    def _call_ocr(self, path: Any, purpose: str) -> dict[str, Any]:  # type: ignore[override]
        self.calls.append(purpose)
        if not self._responses:
            raise AssertionError("补调用次数超出预期")
        return self._responses.pop(0)

    @staticmethod
    def _extract_single_page(path: Any, page_no: int) -> Any:  # type: ignore[override]
        class _Temp:
            def unlink(self, missing_ok: bool = True) -> None:
                return None

        return _Temp()


def _make_pdf(tmp_path: Any) -> Any:
    import pymupdf as fitz

    pdf = tmp_path / "t.pdf"
    document = fitz.open()
    for _ in range(2):
        page = document.new_page()
        page.insert_text((72, 72), "x")
    document.save(str(pdf))
    document.close()
    return pdf


class TestParseDocument:
    def test_页号是1起且每页都有text(self, tmp_path: Any) -> None:
        backend = _StubBackend([_payload([(0, "第一页正文", "stop"), (1, "第二页正文", "stop")])])

        result = backend.parse_document(str(_make_pdf(tmp_path)))

        pages = result.layout["pages"]
        assert [page["page_no"] for page in pages] == [1, 2]
        assert [page["text"] for page in pages] == ["第一页正文", "第二页正文"]
        assert result.parse_method == "deepseek"
        # 主调用只发一次 text_recognition，没有退化页就不该有修补调用
        assert backend.calls == ["text_recognition"]

    def test_退化页换purpose单页重试并替换正文(self, tmp_path: Any) -> None:
        looped = "\n".join(["同一段话反复吐出来"] * 50)
        backend = _StubBackend(
            [
                _payload([(0, "正常正文", "stop"), (1, looped, "length")]),
                _payload([(0, "修补后的正常正文", "stop")]),
            ]
        )

        result = backend.parse_document(str(_make_pdf(tmp_path)))

        assert backend.calls == ["text_recognition", "rich_layout_recognition"]
        assert result.layout["pages"][1]["text"] == "修补后的正常正文"
        assert result.metadata["repaired_pages"] == [2]

    def test_修补仍退化则清空正文交上层兜底(self, tmp_path: Any) -> None:
        """不能把复读正文当成功交出去——那是「假成功」：上层不会当 pending 页处理，
        17000 字的垃圾会一路进 Markdown / 分段 / 归案（实测 617 的 p1 就是这样）。"""
        looped = "\n".join(["同一段话反复吐出来"] * 50)
        backend = _StubBackend([_payload([(0, looped, "length")]), _payload([(0, looped, "length")])])

        result = backend.parse_document(str(_make_pdf(tmp_path)))

        assert result.metadata["repaired_pages"] == []
        assert result.metadata["unrepaired_pages"] == {1: "同一行重复 50 次"}
        assert result.layout["pages"][0]["text"] == ""

    def test_整页只有一张图被判退化并重试(self, tmp_path: Any) -> None:
        backend = _StubBackend(
            [
                _payload([(0, _IMAGE_ONLY, "stop")]),
                _payload([(0, "重试后读出来的正文", "stop")]),
            ]
        )

        result = backend.parse_document(str(_make_pdf(tmp_path)))

        assert result.metadata["repaired_pages"] == [1]
        assert result.layout["pages"][0]["text"] == "重试后读出来的正文"

    def test_未配置Key时报可读错误(self, tmp_path: Any) -> None:
        backend = DeepSeekOCRBackend(api_key="", api_url="https://example.invalid/ocr")
        # _config 会去读 SystemConfig（要 DB）；本用例刻意不碰数据库，直接给它空值。
        with patch.object(DeepSeekOCRBackend, "_config", return_value=""):
            with pytest.raises(Exception, match="DEEPSEEK_OCR_API_KEY"):
                backend.parse_document(str(_make_pdf(tmp_path)))

    def test_文件过大时提前报可操作原因(self, tmp_path: Any) -> None:
        backend = DeepSeekOCRBackend(api_key="test-key", api_url="https://example.invalid/ocr")  # pragma: allowlist secret
        big = tmp_path / "big.pdf"
        big.write_bytes(b"0" * (50 * 1024 * 1024))

        with pytest.raises(Exception, match="实测上限"):
            backend.parse_document(str(big))


class TestRichBlocks:
    def test_解析出块类型与千分比坐标(self) -> None:
        blocks = _parse_rich_blocks(_RICH_PAGE)

        assert [block["type"] for block in blocks] == ["title", "text"]
        assert blocks[0]["text"] == "授权委托书"
        assert blocks[0]["bbox"] == [586.0, 323.0, 704.0, 677.0]

    def test_没有标记的正文不造块(self) -> None:
        assert _parse_rich_blocks("普通正文，没有标记") == []


class TestRegistryAndAvailability:
    def test_已注册到解析器工厂(self) -> None:
        from apps.document_parsing.services.parser_factory import CLOUD_BACKEND_CHOICES, ParserFactory

        assert "deepseek" in ParserFactory._BACKEND_REGISTRY
        assert "deepseek" in CLOUD_BACKEND_CHOICES
        assert "paddleocr_vl" not in CLOUD_BACKEND_CHOICES

    def test_Key未配置时锁定它返回空表(self) -> None:
        from apps.document_parsing.services import parser_factory

        with patch.object(parser_factory, "_deepseek_configured", return_value=False):
            assert parser_factory.resolve_cloud_backends("deepseek") == []

    def test_Key已配置时锁定它只返回它自己(self) -> None:
        from apps.document_parsing.services import parser_factory

        with patch.object(parser_factory, "_deepseek_configured", return_value=True):
            assert parser_factory.resolve_cloud_backends("deepseek") == ["deepseek"]

    def test_auto模式下deepseek排在已注册平台之后(self) -> None:
        from apps.document_parsing.services import parser_factory

        provider = type("P", (), {"provider_type": "mineru", "priority": 5, "pk": 1})()
        with (
            patch.object(parser_factory.ParseProviderService, "get_providers", return_value=[provider]),
            patch.object(parser_factory, "_deepseek_configured", return_value=True),
        ):
            assert parser_factory.resolve_cloud_backends("auto") == ["mineru", "deepseek"]
