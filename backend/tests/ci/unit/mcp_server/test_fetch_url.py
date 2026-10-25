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
