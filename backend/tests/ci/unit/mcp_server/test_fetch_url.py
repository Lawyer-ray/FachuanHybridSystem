"""fetch_url 行为测试 —— 重点是「抓不到时如实报错」。

这个工具的核心风险不是抓不到，而是**假装抓到了**：返回
``{"ok": true, "text": ""}`` 会让模型以为「页面没内容」，而不是「我们被拦了」。
因此下面大半测试都在验证失败分支的 reason 区分是否准确。
"""

from __future__ import annotations

import importlib
from typing import Any
from unittest import mock

import httpx
import pytest


def _module() -> Any:
    """取 ``fetch_url`` **模块**（包 ``__init__`` 里的同名函数会遮蔽模块名）。"""
    return importlib.import_module("mcp_server.tools.web_search.fetch_url")


def _response(status: int = 200, text: str = "", url: str = "https://example.com/") -> httpx.Response:
    return httpx.Response(status_code=status, content=text.encode("utf-8"), request=httpx.Request("GET", url))


@pytest.fixture()
def fake_http() -> Any:
    """替换 fetch_url 内部的 httpx.Client。"""
    with mock.patch.object(_module().httpx, "Client") as patched:
        yield patched


@pytest.fixture(autouse=True)
def _public_dns() -> Any:
    """默认把 DNS 解析 mock 成公网地址。

    SSRF 检查引入了 getaddrinfo 依赖,单测不应触网;个别用例（内网/DNS 失败）
    在测试体内用更内层的 mock.patch 覆盖。
    """

    def _fake_getaddrinfo(host: str, *args: Any, **kwargs: Any) -> list[tuple]:
        ip = "127.0.0.1" if host in ("localhost",) else "93.184.216.34"
        return [(None, None, None, "", (ip, 0))]

    with mock.patch.object(_module().socket, "getaddrinfo", side_effect=_fake_getaddrinfo):
        yield


@pytest.fixture(autouse=True)
def _clear_fetch_cache() -> None:
    """抓取缓存是模块级状态——用例间必须清空,否则后一个用例命中前一个
    用例的缓存,mock 的响应永远不会被触发(假绿)。"""
    _module()._fetch_cache.clear()


def _set_response(fake_http: Any, response: httpx.Response) -> None:
    instance = fake_http.return_value.__enter__.return_value
    instance.get.return_value = response


class TestSuccess:
    def test_extracts_article_text(self, fake_http: Any) -> None:
        html = (
            "<html><head><title>测试标题</title></head><body><article>" + "正文内容。" * 80 + "</article></body></html>"
        )
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a")

        assert result["ok"] is True
        assert result["title"] == "测试标题"
        assert "外部网页抓取内容" in result["text"]  # 注入防御包裹标注
        assert "正文内容" in result["text"]
        assert result["truncated"] is False

    def test_truncates_long_text(self, fake_http: Any) -> None:
        html = "<html><body><article>" + "字" * 5000 + "</article></body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a", max_chars=500)

        assert result["ok"] is True
        assert result["truncated"] is True
        # chars 含包裹标注头尾；正文本体被截到 500 字
        body = result["text"]
        assert "外部网页抓取内容" in body and body.endswith("〔外部网页内容结束〕")
        assert result["chars"] == len(body)
        inner = body.split("〕\n", 1)[1].rsplit("\n〔", 1)[0]
        assert len(inner) == 500

    def test_strips_noise_nodes(self, fake_http: Any) -> None:
        html = (
            "<html><body><article>"
            + "有效正文。" * 60
            + "<script>var evil='x'</script><style>.a{}</style><nav>菜单</nav>"
            + "</article></body></html>"
        )
        _set_response(fake_http, _response(200, html))

        text = _module().fetch_url("https://example.com/a")["text"]
        assert "var evil" not in text
        assert "菜单" not in text

    def test_resolves_sogou_redirect(self, fake_http: Any) -> None:
        """搜狗跳转页要解析出真实地址再抓。"""
        redirect_html = (
            '<meta content="always" name="referrer">'
            '<script>window.location.replace("https://real.example.com/article")</script>'
        )
        real_html = (
            "<html><head><title>真实页</title></head><body><article>" + "原文。" * 100 + "</article></body></html>"
        )

        instance = fake_http.return_value.__enter__.return_value
        instance.get.side_effect = [_response(200, redirect_html), _response(200, real_html)]

        result = _module().fetch_url("/link?url=hedJjaC291PM8os")

        assert result["ok"] is True
        assert result["url"] == "https://real.example.com/article"
        assert result["title"] == "真实页"
        assert instance.get.call_count == 2


class TestHonestFailures:
    """失败必须给准确的 reason，不能伪装成「页面为空」。"""

    def test_antispider_detected(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(200, "<html><body>请输入下方验证码</body></html>"))

        result = _module().fetch_url("https://example.com/a")

        assert result["ok"] is False
        assert result["reason"] == "antispider"
        assert "验证码" in result["message"]

    def test_blocked_403(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(403, "denied"))

        result = _module().fetch_url("https://example.com/a")

        assert result["ok"] is False
        assert result["reason"] == "blocked"

    def test_http_error(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(500, "boom"))

        result = _module().fetch_url("https://example.com/a")

        assert result["ok"] is False
        assert result["reason"] == "http_error"

    def test_timeout(self, fake_http: Any) -> None:
        instance = fake_http.return_value.__enter__.return_value
        instance.get.side_effect = httpx.TimeoutException("slow")

        result = _module().fetch_url("https://example.com/a")

        assert result["ok"] is False
        assert result["reason"] == "timeout"

    def test_network_error(self, fake_http: Any) -> None:
        instance = fake_http.return_value.__enter__.return_value
        instance.get.side_effect = httpx.ConnectError("no route")

        result = _module().fetch_url("https://example.com/a")

        assert result["ok"] is False
        assert result["reason"] == "network_error"

    def test_empty_body_is_javascript_required(self, fake_http: Any) -> None:
        """有壳无内容（SPA）要说「需要 JS」，不能说「页面没内容」。"""
        _set_response(fake_http, _response(200, "<html><body><div id='app'></div></body></html>"))

        result = _module().fetch_url("https://example.com/a")

        assert result["ok"] is False
        assert result["reason"] == "javascript_required"

    def test_invalid_url(self, fake_http: Any) -> None:
        result = _module().fetch_url("ftp://example.com/a")

        assert result["ok"] is False
        assert result["reason"] == "invalid_url"
        fake_http.assert_not_called()

    def test_empty_url(self, fake_http: Any) -> None:
        result = _module().fetch_url("   ")

        assert result["ok"] is False
        assert result["reason"] == "invalid_url"

    def test_never_returns_ok_with_empty_text(self, fake_http: Any) -> None:
        """核心契约：ok=True 时 text 必然非空。"""
        _set_response(fake_http, _response(200, "<html><body></body></html>"))

        result = _module().fetch_url("https://example.com/a")

        assert not (result["ok"] and not result.get("text"))


class TestByteBudgetTruncation:
    """max_chars 按字符计，中文 20000 字符 ≈ 60KB——pi 侧对工具输出按
    20480 字节拦腰截断，截断点落在 JSON 中段，尾部的 truncated 标志模型
    看不到。正文必须按 UTF-8 字节预算**先于 pi** 截断，并保住结束标记。"""

    def test_chinese_max_chars_clamped_by_bytes(self, fake_http: Any) -> None:
        html = "<html><body><article>" + "汉字正文" * 10000 + "</article></body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a", max_chars=20000)

        assert result["ok"] is True
        assert result["truncated"] is True
        assert len(result["text"].encode("utf-8")) <= _module()._BYTE_BUDGET
        assert result["text"].endswith("〔外部网页内容结束〕")

    def test_english_over_budget_clamped(self, fake_http: Any) -> None:
        html = "<html><body><article>" + "word " * 10000 + "</article></body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a", max_chars=20000)

        assert result["truncated"] is True
        assert len(result["text"].encode("utf-8")) <= _module()._BYTE_BUDGET
        assert result["text"].endswith("〔外部网页内容结束〕")

    def test_short_page_not_clamped(self, fake_http: Any) -> None:
        html = "<html><body><article>" + "短页正文。" * 40 + "</article></body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a")

        assert result["truncated"] is False
        assert result["text"].endswith("〔外部网页内容结束〕")

    def test_multibyte_boundary_decodes_safely(self, fake_http: Any) -> None:
        """字节截断点落在多字节字符中间时，解码丢弃残缺字符而非报错。"""
        html = "<html><body><article>" + "汉" * 9000 + "</article></body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a", max_chars=20000)

        assert result["chars"] == len(result["text"])


class TestStartIndexContinuation:
    """分块续读（官方 fetch server 的 max_length + start_index 模式）。

    截断曾是死路：60KB 判决书默认只看到前 6000 字符,尾部**永远读不到**。
    现在返回 total_chars + next_index,truncated=True 时模型把 next_index
    作为下次 start_index 传入即可继续读完。
    """

    @staticmethod
    def _marked_html(blocks: int = 1000) -> str:
        """每块 5 字符（「段」+ 4 位序号）,窗口边界可精确定位。"""
        return "<html><body><article>" + "".join(f"段{i:04d}" for i in range(blocks)) + "</article></body></html>"

    @staticmethod
    def _inner(body: str) -> str:
        return body.split("〕\n", 1)[1].rsplit("\n〔", 1)[0]

    def test_first_chunk_reports_next_index(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(200, self._marked_html()))

        result = _module().fetch_url("https://example.com/a", max_chars=500)

        assert result["ok"] is True
        assert result["truncated"] is True
        assert result["next_index"] == 500
        assert result["total_chars"] == 5000
        assert self._inner(result["text"]).startswith("段0000")

    def test_continuation_returns_following_chunk(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(200, self._marked_html()))

        result = _module().fetch_url("https://example.com/a", max_chars=500, start_index=500)

        inner = self._inner(result["text"])
        assert inner.startswith("段0100")
        assert inner.endswith("段0199")
        assert result["next_index"] == 1000

    def test_final_chunk_next_index_none(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(200, self._marked_html()))

        result = _module().fetch_url("https://example.com/a", max_chars=500, start_index=4500)

        assert result["ok"] is True
        assert result["truncated"] is False
        assert result["next_index"] is None
        assert self._inner(result["text"]).startswith("段0900")

    def test_start_index_beyond_end_returns_note(self, fake_http: Any) -> None:
        """窗口越过末尾不是失败（抓取本身成功）,给明确提示而非空正文。"""
        _set_response(fake_http, _response(200, self._marked_html(blocks=100)))

        result = _module().fetch_url("https://example.com/a", start_index=99999)

        assert result["ok"] is True
        assert result["next_index"] is None
        assert result["truncated"] is False
        assert result["total_chars"] == 500
        assert "没有更多内容" in result["text"]
        # 这条提示是本系统生成的文本,不套外部内容包裹标注
        assert "外部网页抓取内容" not in result["text"]

    def test_byte_clamp_advances_next_index(self, fake_http: Any) -> None:
        """字节刀落在窗口中段时,next_index 按实际送达的前缀推进——
        续读既不跳过未读内容,也不返回 null 谎称读完。"""
        html = "<html><body><article>" + "汉" * 10000 + "</article></body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a", max_chars=20000)

        assert result["truncated"] is True
        assert 0 < result["next_index"] < result["total_chars"]
        assert len(result["text"].encode("utf-8")) <= _module()._BYTE_BUDGET

    def test_negative_start_index_treated_as_zero(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(200, self._marked_html()))

        result = _module().fetch_url("https://example.com/a", max_chars=500, start_index=-50)

        assert result["ok"] is True
        assert self._inner(result["text"]).startswith("段0000")


class TestTableFormatting:
    """表格保真(2026-10-25 审计五十三轮)——法律页面的诉讼费标准/赔偿明细/
    当事人列表全是表格,逐格一行会把行列关系打散成孤字。转成 Markdown 行。"""

    def test_table_becomes_markdown_rows(self, fake_http: Any) -> None:
        html = (
            "<html><body><article>"
            + "<p>诉讼费用标准如下：</p>"
            + "<table><tr><th>标的额</th><th>费率</th></tr>"
            + "<tr><td>10 万以下</td><td>50 元</td></tr>"
            + "<tr><td>10 万 - 20 万</td><td>2%</td></tr>"
            + "</table>"
            + "结语" * 120
            + "</article></body></html>"
        )
        _set_response(fake_http, _response(200, html))
        text = _module().fetch_url("https://example.com/fee")["text"]

        assert "| 标的额 | 费率 |" in text
        assert "| 10 万以下 | 50 元 |" in text
        assert "| 10 万 - 20 万 | 2% |" in text
        # 首行(表头)后跟分隔行,模型能识别这是表格结构
        header_pos = text.index("| 标的额")
        assert text[header_pos:].splitlines()[1].startswith("|---")

    def test_links_inside_cells_keep_text(self, fake_http: Any) -> None:
        html = (
            "<html><body><article>"
            + "<table><tr><th>当事人</th><th>角色</th></tr>"
            + '<tr><td><a href="/x">某建筑公司</a></td><td>被告</td></tr>'
            + "</table>"
            + "正文" * 150
            + "</article></body></html>"
        )
        _set_response(fake_http, _response(200, html))
        text = _module().fetch_url("https://example.com/parties")["text"]

        assert "| 某建筑公司 | 被告 |" in text

    def test_nested_table_formats_recursively(self, fake_http: Any) -> None:
        """嵌套表递归转 pipe 行——政务页常见「单列壳表套真费率表」,直接吸收
        会把行列连成无分隔的「一审3000」。"""
        html = (
            "<html><body><article>"
            + "<table><tr><th>项</th><th>值</th></tr>"
            + "<tr><td>明细</td><td><table><tr><td>一审</td><td>3000</td></tr></table></td></tr>"
            + "</table>"
            + "正文" * 150
            + "</article></body></html>"
        )
        _set_response(fake_http, _response(200, html))
        result = _module().fetch_url("https://example.com/nested")

        assert result["ok"] is True
        assert "| 明细 |" in result["text"]
        # 嵌套表以完整 pipe 行出现,而不是连体文本
        assert "| 一审 | 3000 |" in result["text"]
        assert "一审3000" not in result["text"]

    def test_table_without_rows_leaves_no_debris(self, fake_http: Any) -> None:
        html = (
            "<html><body><article>"
            + "<table><tr><td></td><td></td></tr></table>"
            + "正文" * 150
            + "</article></body></html>"
        )
        _set_response(fake_http, _response(200, html))
        result = _module().fetch_url("https://example.com/empty-table")

        assert result["ok"] is True
        assert "||" not in result["text"]


def _pdf_bytes(pages: list[str], title: str = "") -> bytes:
    """用 pymupdf 生成真 PDF(测试自备证据,不依赖外网)。

    内容用 ASCII 并逐行落位:内置字体渲染不了中文(会变「······」),且单条
    insert_text 不换行、超宽部分不可提取。
    """
    import pymupdf

    doc = pymupdf.open()
    doc.set_metadata({"title": title} if title else {})
    for body in pages:
        page = doc.new_page()
        for line_no, start in enumerate(range(0, len(body), 80), start=1):
            page.insert_text((72, 60 + 12 * line_no), body[start : start + 80], fontsize=10)
    return doc.tobytes()


class TestPdfSupport:
    """PDF 支持(2026-10-25 审计五十四轮)——判决书/通告链接常直接指 PDF;
    此前 response.text 把二进制解成乱码还标 ok=true(%PDF-1.7 当正文喂模型)。"""

    def test_pdf_extracts_text_with_injection_wrap(self, fake_http: Any) -> None:
        pdf = _pdf_bytes(["JUDGMENT PAGE ONE body. " * 20, "JUDGMENT PAGE TWO body. " * 20], title="测试判决书")
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=pdf,
                headers={"content-type": "application/pdf"},
                request=httpx.Request("GET", "https://example.com/j.pdf"),
            ),
        )

        result = _module().fetch_url("https://example.com/j.pdf")

        assert result["ok"] is True
        assert result["title"] == "测试判决书"
        assert "JUDGMENT PAGE ONE" in result["text"]
        # PDF 与网页同一注入攻击面——同一层包裹标注
        assert "外部 PDF 文档抓取内容" in result["text"]
        assert result["text"].rstrip().endswith("〔外部网页内容结束〕")

    def test_pdf_windowing_and_next_index(self, fake_http: Any) -> None:
        pdf = _pdf_bytes(["LONGDOC CONTENT. " * 800])
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=pdf,
                headers={"content-type": "application/pdf"},
                request=httpx.Request("GET", "https://example.com/long.pdf"),
            ),
        )

        result = _module().fetch_url("https://example.com/long.pdf", max_chars=2000)

        assert result["ok"] is True
        assert result["truncated"] is True
        assert result["next_index"] is not None
        assert result["total_chars"] > 5000

        # 续读从 next_index 起,不重不漏
        second = _module().fetch_url("https://example.com/long.pdf", max_chars=2000, start_index=result["next_index"])
        assert second["ok"] is True

    def test_pdf_magic_overrides_wrong_content_type(self, fake_http: Any) -> None:
        """站点给 PDF 配错 content-type(如 text/html)时,字节魔数兜底识别。"""
        pdf = _pdf_bytes(["PLAIN TEXT ROW " * 100])
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=pdf,
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", "https://example.com/oops.pdf"),
            ),
        )

        result = _module().fetch_url("https://example.com/oops.pdf")

        assert result["ok"] is True
        assert "外部 PDF 文档抓取内容" in result["text"]

    def test_scanned_pdf_reports_empty_with_hint(self, fake_http: Any) -> None:
        """无文字 PDF(扫描件形态):能打开但提不出字,如实给 empty_pdf + OCR 提示。"""
        pdf = _pdf_bytes([""])
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=pdf,
                headers={"content-type": "application/pdf"},
                request=httpx.Request("GET", "https://example.com/scan.pdf"),
            ),
        )

        result = _module().fetch_url("https://example.com/scan.pdf")

        assert result["ok"] is False
        assert result["reason"] == "empty_pdf"
        assert "扫描" in result["message"]

    def test_corrupt_pdf_reports_parse_error(self, fake_http: Any) -> None:
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=b"definitely not a pdf",
                headers={"content-type": "application/pdf"},
                request=httpx.Request("GET", "https://example.com/bad.pdf"),
            ),
        )

        result = _module().fetch_url("https://example.com/bad.pdf")

        assert result["ok"] is False
        assert result["reason"] == "pdf_parse_error"

    def test_html_without_pdf_magic_not_treated_as_pdf(self, fake_http: Any) -> None:
        """普通网页不受 PDF 分支影响(content-type 与魔数都不是 PDF)。"""
        html = "<html><body>" + "普通网页正文 " * 300 + "</body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/page")

        assert result["ok"] is True
        assert "外部网页抓取内容" in result["text"]


def _docx_bytes(paragraphs: list[str], table_rows: list[list[str]] | None = None) -> bytes:
    """用 python-docx 生成真 .docx(测试自备证据,不依赖外网)。"""
    import io

    import docx as docx_lib

    document = docx_lib.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    if table_rows:
        table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        for r, cells in enumerate(table_rows):
            for c, text in enumerate(cells):
                table.rows[r].cells[c].text = text
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class TestDocxSupport:
    """Word 支持(2026-10-25 审计五十九轮)——政务通知/规章常用 Word 直链,
    与 PDF 同一病灶:二进制被当 HTML 解成乱码标 ok=true。"""

    def test_docx_extracts_text_and_table(self, fake_http: Any) -> None:
        payload = _docx_bytes(
            ["关于调整律师服务费标准的通知", "各律师事务所:"],
            table_rows=[["标的额", "费率"], ["10 万以下", "50 元"]],
        )
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=payload,
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
                request=httpx.Request("GET", "https://example.com/notice.docx"),
            ),
        )

        result = _module().fetch_url("https://example.com/notice.docx")

        assert result["ok"] is True
        assert result["title"] == "关于调整律师服务费标准的通知"
        assert "各律师事务所" in result["text"]
        assert "| 标的额 | 费率 |" in result["text"]
        assert "| 10 万以下 | 50 元 |" in result["text"]
        assert "外部 Word 文档抓取内容" in result["text"]

    def test_docx_sniffed_via_zip_entry(self, fake_http: Any) -> None:
        """content-type 配错(text/html)时,按 ZIP 内 word/document.xml 判定——
        只看 ZIP 魔数会误伤 xlsx/pptx/epub。"""
        payload = _docx_bytes(["通知正文内容"])
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=payload,
                headers={"content-type": "application/octet-stream"},
                request=httpx.Request("GET", "https://example.com/file"),
            ),
        )

        result = _module().fetch_url("https://example.com/file")

        assert result["ok"] is True
        assert "通知正文内容" in result["text"]

    def test_legacy_doc_reports_parse_error(self, fake_http: Any) -> None:
        """content-type 是 msword 但字节不是 .docx(旧版 .doc)——如实报错并
        提示旧格式不支持,不当乱码成功。"""
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=b"\xd0\xcf\x11\xe0legacy-doc-bytes",
                headers={"content-type": "application/msword"},
                request=httpx.Request("GET", "https://example.com/old.doc"),
            ),
        )

        result = _module().fetch_url("https://example.com/old.doc")

        assert result["ok"] is False
        assert result["reason"] == "docx_parse_error"

    def test_empty_docx_reports_no_text(self, fake_http: Any) -> None:
        payload = _docx_bytes([])
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=payload,
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
                request=httpx.Request("GET", "https://example.com/blank.docx"),
            ),
        )

        result = _module().fetch_url("https://example.com/blank.docx")

        assert result["ok"] is False
        assert result["reason"] == "empty_docx"


class TestEncodingFallback:
    """编码兜底(2026-10-25 审计五十七轮)——老政务/法院站点常只在 meta 里
    声明 gb2312 而响应头不带 charset,httpx 按 utf-8 硬解出 U+FFFD 乱码
    还当 ok=true 交付。头缺失时嗅探 meta;GB 系别名升 gb18030(超集)。"""

    @staticmethod
    def _gb_response(body_html: str, gb_codec: str = "gb2312") -> httpx.Response:
        return httpx.Response(
            200,
            content=body_html.encode(gb_codec),
            headers={"content-type": "text/html"},  # 刻意不带 charset
            request=httpx.Request("GET", "https://gov.example/x.html"),
        )

    def test_meta_gb2312_decodes_chinese(self, fake_http: Any) -> None:
        html = (
            "<html><head><meta http-equiv='Content-Type' content='text/html; charset=gb2312'></head>"
            "<body>最高人民法院公报正文内容测试</body></html>"
        )
        _set_response(fake_http, self._gb_response(html))

        result = _module().fetch_url("https://gov.example/x.html")

        assert result["ok"] is True
        assert "最高人民法院" in result["text"]
        assert "�" not in result["text"]

    def test_gbk_only_char_survives_via_gb18030_upgrade(self, fake_http: Any) -> None:
        """meta 写 gb2312 但正文含 GBK 扩展字(人名生僻字如「镕」)——严格
        gb2312 解不出该字,升 gb18030 后完整。字节按 GBK 落盘(页面作者存
        成 GBK 却声明 gb2312,正是这类站点的真实形态)。"""
        html = "<html><head><meta charset='gb2312'></head><body>委托代理人镕某,正文内容测试。</body></html>"
        _set_response(fake_http, self._gb_response(html, gb_codec="gbk"))

        result = _module().fetch_url("https://gov.example/x.html")

        assert result["ok"] is True
        assert "镕" in result["text"]

    def test_unknown_meta_charset_falls_back_safely(self, fake_http: Any) -> None:
        """meta 编码名不认识时退回默认解码——解码问题绝不能变成异常。"""
        html = "<html><head><meta charset='x-imaginary-9'></head><body>whatever body</body></html>"
        _set_response(
            fake_http,
            httpx.Response(
                200,
                content=html.encode("utf-8"),
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", "https://gov.example/y.html"),
            ),
        )

        result = _module().fetch_url("https://gov.example/y.html")

        assert result["ok"] is True
        assert "whatever body" in result["text"]


class TestRedirectFallback:
    def test_redirect_target_failure_still_reports(self, fake_http: Any) -> None:
        """解析到真实地址但抓取失败时，不能静默当成成功。"""
        redirect_html = '<script>window.location.replace("https://real.example.com/x")</script>'
        instance = fake_http.return_value.__enter__.return_value
        instance.get.side_effect = [
            _response(200, redirect_html),
            httpx.ConnectError("real host down"),
        ]

        result = _module().fetch_url("/link?url=abc")

        # 真实地址抓取失败后，仍返回跳转页本身的分析结果（大概率 javascript_required）
        assert result["ok"] is False
        assert result["reason"] in {"javascript_required", "antispider"}

    def test_redirect_chain_exhaustion_reported_honestly(self, fake_http: Any) -> None:
        """5 跳预算耗尽时如实报 too_many_redirects——旧逻辑会把最后一跳的
        重定向页壳当正文解析,误诊成 javascript_required 或输出壳子乱码。"""
        instance = fake_http.return_value.__enter__.return_value

        def redirect_response(hop: int) -> httpx.Response:
            return httpx.Response(
                302,
                headers={"location": f"https://example.com/r{hop}"},
                request=httpx.Request("GET", f"https://example.com/r{hop - 1}"),
            )

        instance.get.side_effect = [redirect_response(i) for i in range(1, 8)]

        result = _module().fetch_url("https://example.com/entry")

        assert result["ok"] is False
        assert result["reason"] == "too_many_redirects"
        assert "5 跳" in result["message"]

    def test_redirect_without_location_is_http_error(self, fake_http: Any) -> None:
        """302 但无 Location:直说「重定向未提供跳转目标」,不当正文解析。"""
        _set_response(
            fake_http,
            httpx.Response(302, request=httpx.Request("GET", "https://example.com/stuck")),
        )

        result = _module().fetch_url("https://example.com/stuck")

        assert result["ok"] is False
        assert result["reason"] == "http_error"
        assert "未提供跳转目标" in result["message"]


class TestSSRFProtection:
    """SSRF 拦截（2026-10-25 审计）——工具跑在后端同机进程,模型可以让它抓
    127.0.0.1:8002（自家 Django/MCP）、律所内网网关、云元数据端点。命中内网段
    必须拒绝;重定向**手动逐跳跟随**且每跳过检,防「公网 302 → 内网」绕过。
    """

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:8002/admin/",
            "http://localhost:5090/",
            "http://10.1.2.3/x",
            "http://192.168.1.1/router",
            "http://172.16.0.9/",
            "http://172.31.255.255/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]:8080/",
            "http://0.0.0.0/",
            # IPv4-mapped IPv6（2026-10-25 实测绕过口:ipaddress 解析成 IPv6,
            # 与 IPv4 网段的 in 判定恒 False,当年 httpx 经它连上了本机 :8002）
            "http://[::ffff:127.0.0.1]:8002/admin/",
            "http://[::ffff:192.168.1.1]/",
            "http://[::ffff:10.1.2.3]/x",
            # 6to4 / Teredo 过渡格式内嵌的私有 IPv4
            "http://[2002:0a01:0203::]/",
            "http://[2001:0:c0a8:101::]/",
        ],
    )
    def test_internal_targets_blocked(self, url: str) -> None:
        result = _module().fetch_url(url)
        assert result["ok"] is False
        assert result["reason"] == "blocked_target"

    def test_public_ipv6_literal_not_blocked_by_alias_nets(self, fake_http: Any) -> None:
        """拉黑的是「嵌 IPv4 的过渡前缀」,不是整个 IPv6——普通公网 IPv6 字面量
        仍放行到 HTTP 层。"""
        mod = _module()
        _set_response(fake_http, _response(200, "<html><body>" + "正文" * 200 + "</body></html>"))
        result = mod.fetch_url("http://[2606:4700::1111]/")
        assert result.get("reason") != "blocked_target"

    def test_intranet_hostname_blocked(self) -> None:
        """域名解析出内网 IP 同样拦截（按解析结果而非字面判断）。"""
        mod = _module()
        with mock.patch.object(mod.socket, "getaddrinfo", return_value=[(None, None, None, "", ("10.2.3.4", 0))]):
            result = mod.fetch_url("http://intranet.lawfirm.internal/x")
        assert result["ok"] is False
        assert result["reason"] == "blocked_target"

    def test_dns_failure_fails_closed(self) -> None:
        """域名解析失败按内部处理——DNS 异常不应成为绕过口。"""
        mod = _module()
        with mock.patch.object(mod.socket, "getaddrinfo", side_effect=OSError("dns down")):
            result = mod.fetch_url("http://nonexistent.invalid/x")
        assert result["ok"] is False
        assert result["reason"] == "blocked_target"

    def test_public_hostname_allowed_to_proceed(self, fake_http: Any) -> None:
        """公网域名放行到 HTTP 层（不被 SSRF 检查拦）。"""
        mod = _module()
        with mock.patch.object(mod.socket, "getaddrinfo", return_value=[(None, None, None, "", ("93.184.216.34", 0))]):
            _set_response(fake_http, _response(200, "<html><body>" + "正文" * 200 + "</body></html>"))
            result = mod.fetch_url("https://example.com/article")
        assert result.get("reason") != "blocked_target"

    def test_redirect_to_internal_blocked_mid_hop(self, fake_http: Any) -> None:
        """公网 302 → 内网:第二跳必须被拦,而不是自动跟随。"""
        mod = _module()
        with mock.patch.object(mod.socket, "getaddrinfo", return_value=[(None, None, None, "", ("93.184.216.34", 0))]):
            redirect = httpx.Response(
                302,
                headers={"location": "http://127.0.0.1:8002/admin/"},
                request=httpx.Request("GET", "https://evil.com/"),
            )
            _set_response(fake_http, redirect)
            result = mod.fetch_url("https://evil.com/link")
        assert result["ok"] is False
        assert result["reason"] == "blocked_target"


class TestFetchCache:
    """抓取结果缓存(2026-10-25 审计六十四轮)——分块续读长文档时,每个
    chunk 都重新下载+解析整页(4 块判决书 = 4 次完整抓取)。按原始输入
    URL 缓存成功结果的全文,续读直接命中。"""

    @staticmethod
    def _long_html() -> str:
        return "<html><body>" + "<p>判决书正文段落内容。</p>" * 400 + "</body></html>"

    def test_second_call_hits_cache_without_network(self, fake_http: Any) -> None:
        _set_response(fake_http, _response(200, self._long_html()))
        first = _module().fetch_url("https://example.com/judgment", max_chars=2000)

        instance = fake_http.return_value.__enter__.return_value
        instance.get.reset_mock()
        second = _module().fetch_url("https://example.com/judgment", max_chars=2000, start_index=first["next_index"])

        assert second["cached"] is True
        instance.get.assert_not_called()
        # 续读窗口照常按本次参数计算
        assert second["total_chars"] == first["total_chars"]

    def test_expired_entry_refetches(self, fake_http: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        module = _module()
        monkeypatch.setattr(module, "_CACHE_TTL_SECONDS", 0.0)  # 先打补丁:存入即过期
        _set_response(fake_http, _response(200, self._long_html()))
        module.fetch_url("https://example.com/stale", max_chars=2000)

        # TTL=0 存入的条目下一次读取即过期——重新走网络
        again = module.fetch_url("https://example.com/stale", max_chars=2000)

        assert again["cached"] is False

    def test_failures_are_not_cached(self, fake_http: Any) -> None:
        module = _module()
        _set_response(fake_http, httpx.Response(403, request=httpx.Request("GET", "https://example.com/denied")))
        module.fetch_url("https://example.com/denied")

        assert "https://example.com/denied" not in module._fetch_cache
