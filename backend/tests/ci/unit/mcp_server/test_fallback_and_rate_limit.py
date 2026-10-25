"""静默兜底与阻塞限流的回归测试。

这两个问题共享同一个失效模式：**看起来一切正常，实际给出错误体验**。

1. ``as_items`` 曾把无法识别的返回结构静默变成 ``{items: [], total: 0}``，
   后端结构一变，模型就回答「没有数据」——数据在，用户无从察觉；
2. ``web_search`` 限流曾用 ``time.sleep`` 阻塞，实测最长 59 秒，且配额是
   进程级（全所共享），一次高频搜索会拖慢所有人。
"""

from __future__ import annotations

import importlib
import time
from typing import Any
from unittest import mock

import httpx
import pytest


def _web_search_module() -> Any:
    """取 ``web_search`` **模块**（而非同名函数）。

    ``from ...web_search import web_search`` 拿到的是函数；这里要改模块级
    的 ``_last_requests`` / ``_RATE_LIMIT``，必须用 importlib。
    """
    return importlib.import_module("mcp_server.tools.web_search.web_search")


class TestAsItemsNoSilentFallback:
    """``as_items`` 猜不出结构时必须抛错，不能伪造空列表。"""

    def test_list_is_wrapped(self) -> None:
        from mcp_server.client import as_items

        result = as_items([{"id": 1}, {"id": 2}], default_page_size=20)
        assert result["items"] == [{"id": 1}, {"id": 2}]
        assert result["total"] == 2
        assert result["page_size"] == 20

    def test_paged_dict_passes_through(self) -> None:
        from mcp_server.client import as_items

        payload = {"items": [{"id": 1}], "total": 165, "page": 1, "page_size": 20}
        assert as_items(payload) is payload

    def test_unknown_dict_raises(self) -> None:
        """后端改成 {data, count} 时必须报错，而不是让模型以为「共 0 条」。"""
        from mcp_server.client import as_items

        with pytest.raises(TypeError, match="无法识别的返回结构"):
            as_items({"data": [{"id": 1}, {"id": 2}], "count": 2})

    def test_none_raises(self) -> None:
        from mcp_server.client import as_items

        with pytest.raises(TypeError, match="无法识别的返回结构"):
            as_items(None)

    def test_scalar_raises(self) -> None:
        from mcp_server.client import as_items

        with pytest.raises(TypeError):
            as_items(42)


class TestWebSearchRateLimitFailsFast:
    """限流必须快速失败，绝不阻塞调用线程。"""

    @pytest.fixture(autouse=True)
    def _reset_bucket(self) -> Any:
        module = _web_search_module()
        module._last_requests.clear()
        yield
        module._last_requests.clear()

    def test_allows_up_to_limit(self) -> None:
        module = _web_search_module()

        for _ in range(module._RATE_LIMIT):
            module._rate_limit()
        assert len(module._last_requests) == module._RATE_LIMIT

    def test_exceeding_raises_without_blocking(self) -> None:
        """关键断言：超限立即抛错，耗时远小于旧实现的 59 秒。"""
        module = _web_search_module()

        now = time.monotonic()
        module._last_requests[:] = [now - 1] * module._RATE_LIMIT

        started = time.monotonic()
        with pytest.raises(module.RateLimitedError) as excinfo:
            module._rate_limit()
        elapsed = time.monotonic() - started

        assert elapsed < 1.0, f"限流不得阻塞（实测 {elapsed:.2f}s）"
        assert excinfo.value.retry_after >= 1

    def test_expired_entries_are_pruned(self) -> None:
        """窗口外的旧记录要被清掉，否则配额永远不恢复。"""
        module = _web_search_module()

        now = time.monotonic()
        module._last_requests[:] = [now - module._RATE_WINDOW - 5] * module._RATE_LIMIT
        module._rate_limit()

        assert len(module._last_requests) == 1

    def test_search_returns_readable_message_when_limited(self) -> None:
        """超限时返回给模型的是可读提示，而不是异常堆栈。"""
        module = _web_search_module()

        now = time.monotonic()
        module._last_requests[:] = [now - 1] * module._RATE_LIMIT

        message = module._do_search("测试", 5)

        assert isinstance(message, str)
        assert "频繁" in message
        assert "稍后再试" in message


class TestSearchResultInjectionMarking:
    """搜索结果的标题/摘要抓自任意外部网页——必须整体包裹注入防护标注
    （与 ``fetch_url`` 同口径），否则外部内容里的「指令」以裸文本混入
    模型上下文（OWASP LLM06 间接提示注入）。"""

    @pytest.fixture(autouse=True)
    def _reset_bucket(self) -> Any:
        module = _web_search_module()
        module._last_requests.clear()
        yield
        module._last_requests.clear()

    @staticmethod
    def _sogou_html() -> str:
        return (
            "<html><body>"
            '<div class="vrwrap"><h3><a href="/link?url=abc">标题甲</a></h3>'
            '<div class="space-txt">摘要甲</div></div>'
            '<div class="vrwrap"><h3><a href="/link?url=def">标题乙</a></h3>'
            '<div class="space-txt">摘要乙</div></div>'
            "</body></html>"
        )

    def test_results_are_wrapped_with_markers(self) -> None:
        module = _web_search_module()
        response = httpx.Response(
            200,
            content=self._sogou_html().encode("utf-8"),
            request=httpx.Request("GET", "https://www.sogou.com/web"),
        )
        with mock.patch.object(module.httpx, "Client") as patched:
            patched.return_value.__enter__.return_value.get.return_value = response

            result = module._do_search("测试", 5)

        assert result.startswith(module._WRAPPER_HEADER)
        assert result.endswith(module._WRAPPER_FOOTER)
        assert "标题甲" in result and "摘要乙" in result
        assert "2 条搜索结果" in result

    def test_error_messages_are_not_wrapped(self) -> None:
        """限流提示是本系统生成的文本（非外部内容），不包裹。"""
        module = _web_search_module()

        now = time.monotonic()
        module._last_requests[:] = [now - 1] * module._RATE_LIMIT

        message = module._do_search("测试", 5)

        assert module._WRAPPER_HEADER not in message


class TestEmptyResultsHonesty:
    """解析 0 条的如实归因（2026-10-25 真实数据定案）。

    实测搜狗对正常关键词/纯中文乱码/纯 ASCII 乱码**全都**返回可解析的
    模糊匹配结果——解析 0 条几乎必然是反爬页或结构漂移。旧文案
    「未找到相关搜索结果」会让模型对用户做出错误的事实性断言。
    """

    @pytest.fixture(autouse=True)
    def _reset_bucket(self) -> Any:
        module = _web_search_module()
        module._last_requests.clear()
        yield
        module._last_requests.clear()

    @staticmethod
    def _search_with_html(html: str) -> str:
        module = _web_search_module()
        response = httpx.Response(
            200,
            content=html.encode("utf-8"),
            request=httpx.Request("GET", "https://www.sogou.com/web"),
        )
        with mock.patch.object(module.httpx, "Client") as patched:
            patched.return_value.__enter__.return_value.get.return_value = response
            return module._do_search("测试", 5)

    def test_antispider_page_reported_as_blocked(self) -> None:
        message = self._search_with_html("<html><body>请输入下方验证码完成安全验证</body></html>")

        assert "反爬" in message
        assert "未找到相关搜索结果" not in message

    def test_structure_drift_reported_as_parse_anomaly(self) -> None:
        """页面正常返回但结果容器全变了——说「解析异常」而非「未找到」。"""
        message = self._search_with_html(
            "<html><body><div class='brand-new-layout'>搜狗全新结果页结构</div></body></html>"
        )

        assert "解析异常" in message
        assert "换个关键词" in message
        assert "未找到相关搜索结果" not in message

    def test_empty_messages_not_injection_wrapped(self) -> None:
        """归因提示是本系统文本,不套外部内容包裹标注。"""
        module = _web_search_module()
        message = self._search_with_html("<html><body>空壳页无结果</body></html>")

        assert module._WRAPPER_HEADER not in message


class TestPagination:
    """翻页参数(2026-10-25 审计五十五轮)——实测搜狗相邻页结果零重复,
    单页 10 条上限从此不再是能力天花板;每翻一页消耗一次进程级配额。"""

    @pytest.fixture(autouse=True)
    def _reset_bucket(self) -> Any:
        module = _web_search_module()
        module._last_requests.clear()
        yield
        module._last_requests.clear()

    @staticmethod
    def _results_html() -> str:
        return (
            "<html><body>"
            + "<div class='vrwrap'><h3><a href='/link?url=abc'>结果甲</a></h3>"
            + "<div class='space-txt'>摘要甲</div></div>"
            + "</body></html>"
        )

    def _search_capturing(self, page: int) -> tuple[str, Any]:
        import asyncio

        module = _web_search_module()
        response = httpx.Response(
            200,
            content=self._results_html().encode("utf-8"),
            request=httpx.Request("GET", "https://www.sogou.com/web"),
        )
        with mock.patch.object(module.httpx, "Client") as patched:
            instance = patched.return_value.__enter__.return_value
            instance.get.return_value = response
            result = asyncio.run(module.web_search("测试", 5, page=page))
            params = instance.get.call_args.kwargs.get("params")
        return result, params

    def test_page_passed_to_sogou_and_labeled(self) -> None:
        result, params = self._search_capturing(2)

        assert params == {"query": "测试", "page": 2}
        assert "第 2 页" in result

    def test_page_clamped_to_valid_range(self) -> None:
        _, low = self._search_capturing(0)
        _, high = self._search_capturing(99)

        assert low["page"] == 1
        assert high["page"] == 10

    def test_first_page_has_no_page_label(self) -> None:
        result, _ = self._search_capturing(1)

        assert "第 1 页" not in result


class TestNetworkHardening:
    """web_search 网络层对齐(2026-10-25 审计六十八轮)——与 fetch_url/
    client.py 同一纪律:忽略系统代理变量(本机代理会把直连可达的搜狗
    代理出去表现为超时);结果页超 10MB 视为劫持/异常,放弃解析。"""

    @pytest.fixture(autouse=True)
    def _reset_bucket(self) -> Any:
        module = _web_search_module()
        module._last_requests.clear()
        yield
        module._last_requests.clear()

    def test_trust_env_disabled(self) -> None:
        import asyncio

        module = _web_search_module()
        response = httpx.Response(
            200,
            content=b"<html><body></body></html>",
            request=httpx.Request("GET", "https://www.sogou.com/web"),
        )
        with mock.patch.object(module.httpx, "Client") as patched:
            instance = patched.return_value.__enter__.return_value
            instance.get.return_value = response
            asyncio.run(module.web_search("测试", 5))

            kwargs = patched.call_args.kwargs
        assert kwargs.get("trust_env") is False

    def test_oversized_result_page_abandoned(self) -> None:
        import asyncio

        module = _web_search_module()
        huge = httpx.Response(
            200,
            content=b"x" * (10 * 1024 * 1024 + 1),
            request=httpx.Request("GET", "https://www.sogou.com/web"),
        )
        with mock.patch.object(module.httpx, "Client") as patched:
            instance = patched.return_value.__enter__.return_value
            instance.get.return_value = huge
            result = asyncio.run(module.web_search("测试", 5))

        assert "响应体过大" in result


class TestResultSourceInfo:
    """结果来源站点(2026-10-25 审计五十八轮)——搜狗 citeLinkClass 带真实
    站点名+域名,提取到结果行让模型不抓原文就能评估来源权威性并正确引用。"""

    @staticmethod
    def _results_html(with_cite: bool) -> str:
        cite = (
            "<a class='citeLinkClass'><span>最高人民法院</span>"
            "<span>https://www.court.gov.cn/zixun/...</span>"
            "<span class='cite-date'>3天前</span></a>"
            if with_cite
            else ""
        )
        return (
            "<html><body><div class='vrwrap'><h3><a href='/link?url=x'>裁判文书公开</a></h3>"
            f"<div class='space-txt'>摘要内容</div>{cite}</div></body></html>"
        )

    def _parse(self, html: str) -> list[Any]:
        module = _web_search_module()
        return module._parse_results(html, 5)

    def test_source_site_and_host_extracted(self) -> None:
        results = self._parse(self._results_html(with_cite=True))

        assert results[0].source == "最高人民法院（www.court.gov.cn）"

    def test_source_line_in_search_output(self) -> None:
        module = _web_search_module()
        response = httpx.Response(
            200,
            content=self._results_html(with_cite=True).encode("utf-8"),
            request=httpx.Request("GET", "https://www.sogou.com/web"),
        )
        module._last_requests.clear()
        with mock.patch.object(module.httpx, "Client") as patched:
            patched.return_value.__enter__.return_value.get.return_value = response
            output = module._do_search("测试", 5)

        assert "来源: 最高人民法院（www.court.gov.cn）" in output

    def test_missing_cite_degrades_to_no_source(self) -> None:
        results = self._parse(self._results_html(with_cite=False))

        assert results[0].source == ""
