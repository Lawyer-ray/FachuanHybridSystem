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

        message = module._do_search("测试", 5, "cn-zh")

        assert isinstance(message, str)
        assert "频繁" in message
        assert "稍后再试" in message
