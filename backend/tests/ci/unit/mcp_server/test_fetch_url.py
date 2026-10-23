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
        assert result["text"].startswith("正文内容")
        assert result["truncated"] is False

    def test_truncates_long_text(self, fake_http: Any) -> None:
        html = "<html><body><article>" + "字" * 5000 + "</article></body></html>"
        _set_response(fake_http, _response(200, html))

        result = _module().fetch_url("https://example.com/a", max_chars=500)

        assert result["ok"] is True
        assert result["truncated"] is True
        assert result["chars"] == 500

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
