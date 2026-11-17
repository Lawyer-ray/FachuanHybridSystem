"""法院/政务 httpx 客户端必须无视进程级代理环境变量。

## 背景（2026-11-17 任务 344 真实事故）

``backend/.env`` 里有 ``HTTPS_PROXY=http://127.0.0.1:7897``（本地代理软件），
``load_dotenv()`` 把它注入 ``os.environ``。当天代理没开，端口无监听，于是
法院直连 API 每次都是 ``ConnectError: [Errno 61] Connection refused``，
日志只显示「直接 API 连续 3 次调用失败」，完全看不出是代理导致，
最终降级到浏览器又被「身份核验」拦住，任务全灭。

``court_client()`` 固定 ``trust_env=False``，让这批国内政务直连绕开代理。
本测试锁死这条契约：**即使进程里注入了一个不可达的代理，也绝不能让它生效**。
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest

from apps.automation.services.scraper.scrapers.court_document._http import court_client

_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


@pytest.fixture(autouse=True)
def _restore_proxy_env() -> Iterator[None]:
    """无论用例结果如何都还原代理环境变量，避免污染其他用例。"""
    saved = {k: os.environ.get(k) for k in _PROXY_KEYS}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_ignores_unreachable_proxy_from_env() -> None:
    """注入一个死代理：court_client 的 mounts 里不能出现它。"""
    os.environ["HTTP_PROXY"] = "http://127.0.0.1:7897"
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"

    with court_client(timeout=5.0) as client:
        assert client.trust_env is False
        # trust_env=False ⇒ 不挂任何代理 transport
        mounted = [v for v in client._mounts.values() if v is not None]
        assert not any(isinstance(m, httpx.HTTPTransport) and m._pool for m in mounted)


def test_plain_httpx_would_pick_up_proxy() -> None:
    """对照：裸 httpx.Client 会读到代理——证明上一测试确实在防真实差异。"""
    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"
    with httpx.Client() as client:
        assert client.trust_env is True
        mounted = [v for v in client._mounts.values() if v is not None]
        assert mounted, "裸 httpx.Client 应挂上代理 transport"


def test_caller_cannot_reenable_trust_env() -> None:
    """调用方误传 trust_env=True 也会被覆盖——刻意设计，防止漏配。"""
    with court_client(trust_env=True) as client:
        assert client.trust_env is False


def test_forwards_other_kwargs() -> None:
    """其余参数照常透传（timeout / follow_redirects / headers）。"""
    with court_client(timeout=12.0, follow_redirects=True, headers={"X-Test": "1"}) as client:
        assert client.follow_redirects is True
        assert client.headers["X-Test"] == "1"
