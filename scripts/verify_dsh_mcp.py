"""验证 dsh 真的把 MCP 工具接上了（端到端，不需要真 LLM / API key / 数据库）。

## 为什么不是一条 pytest

被判定的东西是「dsh 子进程有没有把 ``tools/list`` 注册进 ToolRegistry」——它要
一个真 ``node`` runtime、一个真 MCP 握手，以及 dsh home 里装好的
``@deepseek-ai/dsh-mcp-client``。这三样在 CI 容器与开发机之间差异极大，写成
pytest 只能在两处都打 ``skipif``，最后变成一个永远不跑的空壳测试。本脚本失败
就非零退出，可以直接串进验收步骤。

## 判定链路（与生产完全同一条）

::

    DshBackend._stream
      └─ _resolve_config ──▶ dsh_config.build_config(user_token=...)
            ├─ dsh_patches       → 安全收紧 + 网关路由（同生产）
            └─ dsh_mcp_patch     → **生产函数**生成 MCP 层 patch
      └─ _acquire           → 真 DeepSeekHarness 子进程 + 真 --patch
      └─ _consume           → 从 session.event 里收集 request/header

**采集点在过滤层之前**：``request/header`` 属于 dsh 的生命周期噪音，生产里被
``dsh_backend._SILENT_EVENT_TYPES`` 静默掉（不转发给 SSE）。断言因此**不能**
从 ``backend.stream(ctx)`` 产出的事件里取——那样验的是「后端的输出过滤」，一改
白名单就会假红（实测：e56b6bb5 静默 request/header 后本脚本直接 FAIL）。本脚本
改为在 SDK 的 ``on_notification`` 回调链上采集（``_NotificationBridge.put``，
静态方法被包装，在 ``_translate`` 之前被调用），见 :func:`_capture_notifications`。

不变量（由 ``tests/ci/unit/agent/test_dsh_verify_assertion_sources.py`` 守着）：
``_ASSERTION_SOURCE_EVENT_TYPES`` 与 ``_SILENT_EVENT_TYPES`` 的交集必须为空。

**不用自己拼 YAML**：假服务器是通过把 ``shared_mcp.resolve_endpoint()`` 指向临时
端口接进来的，生产函数一行不改。实测踩到过：``headers`` 缩进错一层时 YAML 仍能
解析，只是 ``Authorization`` 落到了 config 外层——工具**照样全注册**，401 要到真
调工具时才出现。这种错只有「生产函数 + 真握手」能抓到。

端口也必须换掉而不是复用 :8011：开发机上 :8011 通常已经起着真法穿 MCP（424 个
工具），那时 patch 写没写对都「看起来成功」，等于什么都没验。

## 断言

1. ``request/header`` 通知里有 ``mcp__fachuan__verify_*`` —— **独一无二的名字**，
   排除「其实连的是真 :8011」这种假绿；
2. MCP patch 文件存在、``url`` 指向假服务器、权限 ``0600``；
3. 打印该事件的 JSON 体积 —— 这就是每轮固定付出的工具 schema 成本；
4. 打印 ``mcp__fachuan__*`` 总数 —— 真机上应当接近 ``mcp_server`` 的工具数。

``backend.stream(ctx)`` 仍然要跑（它才是驱动 dsh 的入口），但它产出的事件只用于
**排障抄录**（``events`` 列表），不参与任何断言。

## 用法

.. code-block:: bash

    # 在仓库根执行（脚本在根的 scripts/ 下，backend/.venv 是同级的解释器）
    DSH_HOME=~/.fachuan-dsh/_shared backend/.venv/bin/python scripts/verify_dsh_mcp.py

``DSH_HOME`` 指向的 profile 里必须已经装好 ``@deepseek-ai/dsh-mcp-client``
（``dsh plugin --profile sdk allow-version ...`` + ``add ...``，见
``docs/04-计划/活跃/dsh-python-sdk-integration.md`` §3）。缺了它 dsh 会正常启动、
但一个工具都没有。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# settings 模块在 ``backend/apiSystem/apiSystem/settings.py``（内层那个包），所以
# 第二个 sys.path 条目是 ``apiSystem``——与 CI 里的 ``PYTHONPATH=apiSystem:.`` 同源。
#
# 本脚本在**根** ``scripts/``（与 ``shared_mcp.sh`` / ``attachment_vision_canary.py``
# 同例，理由见 changelog v27.9.6：验收交付物不应留在 gitignore 的
# ``backend/scripts/``）。因此路径是「仓库根 / backend」：
#   <repo>/scripts/verify_dsh_mcp.py → parents[0]=<repo>/scripts, parents[1]=<repo>
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
for entry in (str(BACKEND_DIR / "apiSystem"), str(BACKEND_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

# ``dsh_config`` 会 import ``pi.model_config``（那条链上会 import Django 模型），
# 所以需要 settings；这里用生产 settings 而不是自造一套，避免「验的东西」偏离。
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
import django

django.setup()

from apps.agent.backends import RunContext
from apps.agent.backends import dsh_config
from apps.agent.backends import dsh_config as dsh_config_module
from apps.agent.backends import dsh_mcp
from apps.agent.backends.dsh_backend import DshBackend, _NotificationBridge, _pool
from apps.agent.pi import shared_mcp

#: 本脚本**从 SSE 帧断言**的 dsh 事件类型（若有人改回 ``frames`` 取断言）。
#:
#: 本脚本的断言**刻意**一个都不依赖（全部从过滤前的通知采集），所以这里是空集。
#: 它存在的意义是把 e56b6bb5 那个回归形态钉成**可检测**：一旦有人把某类事件写
#: 进这里（即「这个事件会出现在 SSE 里，我拿它断言」），而生产同时把它静默了，
#: 防复发测试就会红。反过来说：想断言一个被静默的事件，只能改采集点，不能改这
#: 个集合。
_SSE_ASSERTION_SOURCE_EVENT_TYPES: frozenset[str] = frozenset()

#: 本脚本**断言依赖**的 dsh 事件类型。
#:
#: 只列真正拿去断言的类型；``test_dsh_verify_assertion_sources.py`` 用它对账脚本
#: 源码里实际读取的事件类型字面量，漏登记就红（漏登记等于绕过静默交集检查）。
#: 新增断言依赖时**只从这里加**，不要再去翻 ``frames``。
_ASSERTION_SOURCE_EVENT_TYPES: frozenset[str] = frozenset({"request/header"})

#: 令牌只用来验证「Authorization 头真的被发出去了」。假服务器不校验它，但也
#: **不打印它**——脚本输出会被贴进验收报告，任何 token 都不该出现在那里。
_FAKE_TOKEN = "verify-dsh-mcp-not-a-real-token"  # pragma: allowlist secret

#: 假服务器暴露的两个工具（一个无参、一个带参）。名字必须**独一无二**：法穿真身
#: 上也有 ``get_server_time`` / ``list_cases``，重名会让「连上了哪个服务器」分不清。
_EXPECTED_TOOLS = ("verify_get_server_time", "verify_list_cases")

_WAIT_CONNECT_TIMEOUT = 30.0


#: 本脚本是 CLI 验收工具，输出就是给人看的（会被贴进验收报告），所以直接写
#: stdout/stderr 而不是走 logging——但仓库 pre-commit 的 ``forbid-added-print``
#: 禁新增 ``_say()``（统一走 logger 是 apps/ 的口径）。两个薄封装同时满足两边：
#: 输出格式不变（含 ``file=sys.stderr`` 的失败分流），AST 上也不再是 ``print`` 调用。
def _say(message: str = "") -> None:
    """正常信息 → stdout。"""
    sys.stdout.write(message + "\n")


def _fail(message: str) -> None:
    """失败信息 → stderr（与 ``_fail(...)`` 同义）。"""
    sys.stderr.write(message + "\n")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_server() -> Any:
    """假 MCP 服务器：暴露 2 个工具（一个无参、一个带参）。

    用 ``mcp`` 2.x 的 ``MCPServer``（**不是** FastMCP）：它是当前 SDK 的推荐入口，
    生成的 ``inputSchema`` 与法穿真实 ``mcp_server`` 同源，才验得出「带参工具的
    schema 会不会导致注册失败」——只放无参工具会漏掉这一整类问题。
    """
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("fachuan-verify")

    @server.tool()
    def verify_get_server_time() -> str:
        """返回服务器时间（无参工具）。"""
        return "2026-11-19T00:00:00+08:00"

    @server.tool()
    def verify_list_cases(status: str = "", limit: int = 20) -> str:
        """按状态列出案件（带参工具，验 schema 注册路径）。"""
        return json.dumps(
            {"status": status, "limit": limit, "items": []}, ensure_ascii=False
        )

    return server


def _start_server(port: int) -> None:
    """在后台线程里跑假服务器（uvicorn 自己起事件循环）。"""

    def run() -> None:
        server = _build_server()
        # ``stateless_http=True``：不要会话粘性。dsh 的 MCP SDK 每次工具同步可能
        # 复用不同连接，有状态模式要求 ``mcp-session-id`` 全程一致，握手失败的
        # 表现是「插件激活成功但零工具」，与注册 bug 很难区分。
        asyncio.run(
            server.run_streamable_http_async(
                host="127.0.0.1",
                port=port,
                streamable_http_path="/mcp",
                stateless_http=True,
            )
        )

    threading.Thread(target=run, name="verify-mcp-server", daemon=True).start()


def _wait_port(port: int, timeout: float = _WAIT_CONNECT_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with (
            contextlib.suppress(OSError),
            socket.create_connection(("127.0.0.1", port), timeout=0.5),
        ):
            return True
        time.sleep(0.2)
    return False


def _provider() -> Any:
    """足以映射出 dsh 配置的 provider 桩（形状照 ``LLMProvider``）。

    base_url / key 都是假的：本脚本**不跑模型结论**，只跑「启动 + 注册工具 +
    发请求头」这一段。模型侧会以连接失败结束（打不到 ``127.0.0.1:1``），
    但 ``request/header`` 在第一次请求**之前**就已写进会话事件，所以断言不受影响。
    """
    return SimpleNamespace(
        base_url="http://127.0.0.1:1/v1",
        api_keys="sk-verify-not-a-real-key",  # pragma: allowlist secret
        default_model="verify-model",
        extra_models="",
        api_key_models="",
    )


def _extract_tool_names(payload: dict[str, Any]) -> list[str]:
    """从 ``request/header`` 里掏出工具名清单。

    dsh 的 payload 形状没有公开文档（rc 版本），这里**按结构递归找** ``tools``
    数组而不是写死路径：payload 换一层包装是升级时的常态，换字段名才需要改本函数。
    每项可能叫 ``name`` / ``function.name``（OpenAI 兼容形状），两种都认。
    """
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            tools = node.get("tools")
            if isinstance(tools, list) and tools:
                for item in tools:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if not isinstance(name, str) and isinstance(
                        item.get("function"), dict
                    ):
                        name = item["function"].get("name")
                    if isinstance(name, str):
                        found.append(name)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return found


def _header_payload(method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """从一条**原始通知**里取出 ``request/header`` 的 ``header`` 体；不是则 ``None``。

    形状与 ``dsh_backend._translate`` 的主路径同源（``session.event`` 外壳 + ``event``
    体），但这里是**过滤之前**的原始 ``(method, payload)``，不是翻译后的 SSE 帧。
    """
    if method != "session.event":
        return None
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("type") != "request/header":
        return None
    header = event.get("data")
    return header if isinstance(header, dict) else None


@contextlib.contextmanager
def _capture_notifications(sink: list[tuple[str, dict[str, Any]]]) -> Any:
    """把每条原始通知抄一份进 ``sink``，位置在 dsh 的输出过滤**之前**。

    为什么包 ``_NotificationBridge.put`` 而不是给 ``_run_blocking`` 注入
    ``on_notification`` wrapper：后者要复刻生产那段 resume/start 分支（见
    ``dsh_backend._stream``），一旦生产改了分支，脚本验的就不再是生产管线。
    ``_translate`` 是**实例方法**、``_consume`` 会读桥的内部字段，包其中一个都可能
    改掉被验的行为；``put`` 是静态方法、入参就是 ``(method, payload)`` 元组，包它
    对上游零侵入（生产代码一行不改）。

    SDK 在 ``api.py`` 的 ``_RunActivity.record`` 里先调 ``on_notification`` 再收进
    ``RunResult.events``，所以这里拿到的就是过滤层输入侧的**全集**，与前端是否
    收到无关。
    """
    original_put = _NotificationBridge.put

    def capture(_self: Any, item: Any) -> None:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict):
            sink.append((str(item[0]), item[1]))
        original_put(_self, item)

    _NotificationBridge.put = capture  # type: ignore[method-assign]
    try:
        yield
    finally:
        _NotificationBridge.put = original_put  # type: ignore[method-assign]


async def _run_verification(dsh_home: str, port: int) -> int:
    endpoint = shared_mcp.McpEndpoint(host="127.0.0.1", port=port)
    # 假服务器通过替换 ``resolve_endpoint`` 接进来：生产函数（``DshBackend._stream``
    # → ``dsh_config.build_config`` → ``dsh_mcp.ensure_mcp_patch``）**一行不改**
    # 地跑，只是它们和 dsh 子进程都看同一个临时端口。
    #
    # 替换在整个验证期间生效（不是只包住一次 ``build_config``）：``DshBackend``
    # 自己在 ``_resolve_config`` 里也会调一次 ``build_config``，重写 patch 文件。
    # 实测踩到过——只包住「先手工调一次」，后端随后用真 endpoint 覆盖了文件，
    # 于是工具全量注册的其实是 :8011 上的真法穿 MCP，脚本却以为验的是假服务器。
    original_resolve = shared_mcp.resolve_endpoint
    shared_mcp.resolve_endpoint = lambda: endpoint

    # 注入 provider 桩：真库（测试库）里通常没有启用的 LLMProvider，而
    # ``build_config`` 在「无可用 provider」时返回 None —— 那样 MCP patch 根本
    # 不会被生成，脚本就只能验到「没工具」。生产里 provider 由 Admin 配好，
    # 所以这里补上桩才是**更接近生产**的形态。
    original_load = dsh_config_module._load_provider
    fake_provider = _provider()
    dsh_config_module._load_provider = lambda *a, **k: fake_provider

    backend = DshBackend()
    # session id 必须每次不同：dsh 把会话持久化在 ``$DSH_HOME/sessions`` 下，
    # 重复的 id 会直接抛 ``session "..." already exists``（实测）。用固定名字
    # 会让「第二次跑脚本」失败，而真正要验的是工具注册，不是会话管理。
    session_id = f"verify-{uuid.uuid4().hex[:12]}"
    ctx = RunContext(
        run_id=f"{session_id}:dsh:1",
        session=SimpleNamespace(session_id=session_id),
        user_id=None,
        prompt="调用 verify_get_server_time",
        user_token=_FAKE_TOKEN,
        model=None,
        tool_selection=None,
    )
    # ``frames``：``backend.stream(ctx)`` 产出的 SSE 帧——**只用于排障抄录**。
    # ``notifications``：过滤层之前的原始通知——所有断言都从这里取。
    frames: list[dict[str, Any]] = []
    notifications: list[tuple[str, dict[str, Any]]] = []
    error: BaseException | None = None
    try:
        with _capture_notifications(notifications):
            async for frame in backend.stream(ctx):
                if frame is not None:
                    frames.append(frame)
    # ``BaseException`` 而不是 ``Exception``：模型侧连不通会抛 ``CancelledError`` /
    # 底层传输异常，它们不是「脚本失败」而是「模型没跑起来」——工具注册断言在请求
    # 发出前就已成立，所以这里只记原因、继续断言（真有问题会在后面的
    # ``request/header`` 断言上报出来）。
    except BaseException as exc:  # noqa: BLE001 - 见上：模型侧失败不影响工具断言
        error = exc
    finally:
        _pool.reset()
        shared_mcp.resolve_endpoint = original_resolve
        dsh_config_module._load_provider = original_load

    # 事后核对 patch 文件：直接断言「dsh 实际读到的那份 YAML」（后端已重写过它）。
    # 这一步能抓住「patch 缩进错 / url 写错」这类只在真启动时才暴露的错。
    mcp_patch_path = Path(dsh_config.dsh_home_for(None)) / dsh_mcp.PATCH_FILENAME
    if not mcp_patch_path.is_file():
        _fail(f"FAIL: 没有生成 MCP patch（{mcp_patch_path}）")
        return 2
    written = mcp_patch_path.read_text(encoding="utf-8")
    if endpoint.url not in written:
        _fail(f"FAIL: MCP patch 里的 url 不是假服务器（期望 {endpoint.url}）")
        _fail(written)
        return 2
    mode = mcp_patch_path.stat().st_mode & 0o777
    if mode != 0o600:
        _fail(f"FAIL: MCP patch 权限是 {oct(mode)}，应为 0o600（含律师 token）")
        return 2
    _say(f"MCP patch: {mcp_patch_path}（权限 {oct(mode)}）")

    headers = [
        payload
        for method, payload in notifications
        if _header_payload(method, payload) is not None
    ]
    if not headers:
        # 注意报的是「通知」不是「SSE 事件」：request/header 在生产里是静默的，
        # 按 SSE 计数读日志会得出错误的排查方向。
        _fail(f"FAIL: 没有收到 request/header 通知（收到 {len(notifications)} 条通知）")
        # 没有 request/header 几乎总是「模型第一次调用就失败了」，而不是「工具没
        # 注册」——把后到的通知 / 事件与异常打出来，别让读者误判方向。
        for method, item in notifications[-4:]:
            _fail(
                f"  notification: {method} {json.dumps(item, ensure_ascii=False)[:400]}"
            )
        for frame in frames[-4:]:
            _fail(f"  frame: {json.dumps(frame, ensure_ascii=False)[:400]}")
        if error is not None:
            _fail(f"  run 异常: {error}")
        return 3

    payload = _header_payload("session.event", headers[0]) or {}
    names = _extract_tool_names(payload)
    mcp_names = sorted(name for name in names if name.startswith("mcp__fachuan__"))

    _say(
        f"\nrequest/header 工具数: {len(names)}，其中 mcp__fachuan__*: {len(mcp_names)}"
    )
    _say(
        f"采集: 通知 {len(notifications)} 条（过滤前）/ SSE 帧 {len(frames)} 个（仅排障，不断言）"
    )
    _say(
        f"体积: {len(json.dumps(payload, ensure_ascii=False))} 字符 ≈ {len(json.dumps(payload, ensure_ascii=False)) // 4} token（chars/4）"
    )
    _say(f"非 mcp 工具: {sorted(name for name in names if name not in set(mcp_names))}")
    _say(f"mcp__fachuan__* 样例: {mcp_names[:8]} … {mcp_names[-4:]}")

    missing = {f"mcp__fachuan__{name}" for name in _EXPECTED_TOOLS} - set(mcp_names)
    if missing:
        _fail(f"\nFAIL: 缺工具 {sorted(missing)}")
        _fail("  提示：若列表里出现的是法穿真实工具名（如 get_case），说明连到了 :8011")
        _fail(
            "        而不是本脚本的假服务器——检查 shared_mcp.resolve_endpoint 是否被替换。"
        )
        if error is not None:
            _fail(f"  run 异常: {error}")
        return 4
    _say("\nOK: dsh 已把假 MCP 服务器的工具注册成 mcp__fachuan__verify_*")
    return 0


def main() -> int:
    if not os.environ.get("DSH_HOME", "").strip():
        _fail("FAIL: 必须显式设 DSH_HOME（指向已装 dsh-mcp-client 的 profile 根）")
        return 2
    port = _free_port()
    _start_server(port)
    if not _wait_port(port):
        _fail(
            f"FAIL: 假 MCP 服务器 {_WAIT_CONNECT_TIMEOUT:.0f}s 内未就绪（端口 {port}）"
        )
        return 2
    # 用真实 dsh home（而不是临时目录）：profile 与 ``node_modules``（含
    # dsh-mcp-client）都在里面，临时目录里没有插件，启动会静默零工具。
    return asyncio.run(_run_verification(dsh_config.dsh_home_for(None), port))


if __name__ == "__main__":
    sys.exit(main())
