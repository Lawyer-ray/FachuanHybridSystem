"""tests/ci/unit 的共享 fixture。

这里只放**进程级共享状态**的隔离，不放业务 fixture（业务 fixture 就近放在各自目录）。
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest

from apps.core.llm.key_pool import reset_shared_pools


@pytest.fixture(autouse=True)
def _isolate_shared_key_pools() -> Iterator[None]:
    """每个用例前后清空进程级 Key 池。

    Key 池按「平台名 + Key 列表 + 每 Key 上限 + 白名单」内容寻址并在**进程内复用**
    （服务路径与 Agent 路径共用同一注册表），因此失败冷却与在途计数是跨用例共享的状态：
    某个用例把 ``(Key, 模型)`` 打进 30 秒冷却后，后面用同一个池的用例就选不到该 Key，
    表现为「单独跑通过、一起跑失败」。
    """
    reset_shared_pools()
    yield
    reset_shared_pools()


@pytest.fixture(autouse=True)
def _isolate_web_search_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """每个用例前后清空 ``web_search`` 的进程级熔断与结果缓存。

    两者都是**跨用例共享的模块级状态**（共享 MCP 是常驻进程，本来就是进程级）：
    前一个用例把搜狗桌面通道打进 10 分钟冷却后，后面断言「解析异常」的用例
    会直接拿到「冷却中」，表现为「单独跑绿、一起跑红」。缓存同理——
    上一个用例缓存的输出会让下一个用例的 mock 响应永远不被触发（假绿）。

    导入放在函数内：本包只依赖 stdlib + bs4/httpx，但 ``mcp_server.tools``
    的导入链会碰 Django 配置，收集期导入会把「非 agent 用例」也拖下水。

    同时**屏蔽兜底检索通道的环境变量**：开发机 ``.env`` 里通常配着律所网关
    （``FACHUAN_FIRM_SEARCH_*``），不屏蔽的话「三通道全失败」的用例会真的去打
    公网网关——mock 掉 ``httpx.Client`` 时还会因为 ``resp.status_code`` 是
    MagicMock 而炸在 ``>= 400``（2026-11-21 踩过：单独跑绿、一起跑红）。
    单测必须与开发机的 .env 无关。
    """
    try:
        firm = importlib.import_module("mcp_server.firm_search")
        monkeypatch.delenv(firm.ENV_URL, raising=False)
        monkeypatch.delenv(firm.ENV_KEY, raising=False)
        # 平台配置解析也屏蔽：单测的测试库里没有 LLMProvider，
        # 真去查库既慢又会把「查库异常」混进失败原因（真实告警会被噪声淹没）。
        monkeypatch.setattr(firm, "_active_providers", list)
    except Exception:  # pragma: no cover - 模块不可导入时不该让全量用例挂掉
        pass
    try:
        module = importlib.import_module("mcp_server.tools.web_search.web_search")
    except Exception:  # pragma: no cover - 未安装该依赖的场景不该让全量用例挂掉
        yield
        return
    module._BREAKER.reset()
    module._CACHE.clear()
    module._last_requests.clear()
    yield
    module._BREAKER.reset()
    module._CACHE.clear()
    module._last_requests.clear()
