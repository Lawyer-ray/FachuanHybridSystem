"""法院/政务站点专用 httpx 客户端工厂。

## 为什么必须 ``trust_env=False``

法院文书下载全部是**国内政务直连**（zxfw.court.gov.cn、hbfy.gov.cn、
各级法院 OSS），不该经过任何出口代理。但 ``httpx.Client()`` 默认
``trust_env=True``，会读 ``os.environ`` 里的 ``HTTP_PROXY`` / ``HTTPS_PROXY``。

真实事故（2026-11-17，任务 344）：

``backend/.env`` 里写着 ``HTTPS_PROXY=http://127.0.0.1:7897``（本地代理软件），
 ``load_dotenv()`` 把它注入了 ``os.environ``。当天代理软件没开，端口无监听，
 于是每一次直连 API 都变成：

    ConnectError: [Errno 61] Connection refused

 而当时的日志只说「直接 API 连续 3 次调用失败」，看不出是代理问题；风控上
 也完全没有必要——法院站点在国内，走代理反而更慢更不稳。

 ``trust_env=False`` 让这批请求**无视进程级代理环境变量**：代理软件开或没开，
 法院下载都走直连。副作用是也不会读 ``NETRC`` / ``SSL_CERT_FILE``——政务站点
 用公共 CA，不需要这两者。

## 代理软件确实需要时的出口

 真要给法院流量上代理，应该在 ``proxies=`` 显式传参（按需、可审计），
 而不是让它从环境变量里悄悄漏进来。
"""

from __future__ import annotations

from typing import Any

import httpx


def court_client(**kwargs: Any) -> httpx.Client:
    """创建法院/政务站点专用同步客户端（强制直连，忽略进程代理环境变量）。

    传参同 ``httpx.Client``；``trust_env`` 由本函数固定为 ``False``，
    调用方即使误传也会被覆盖——这是刻意的，避免再出现「某处漏配代理」。
    """
    kwargs.pop("trust_env", None)
    return httpx.Client(trust_env=False, **kwargs)
