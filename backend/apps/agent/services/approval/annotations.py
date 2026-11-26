"""MCP 工具注解表 —— 进程内懒加载一次，供风险分级做「补漏层」。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ...backends.toolface import tool_prefix

logger = logging.getLogger(__name__)

#: 业务 MCP 工具的前缀（``mcp__fachuan__``），与审批分级同源。
MCP_TOOL_PREFIX = tool_prefix()


def _list_mcp_tools(mcp: Any) -> list[Any]:
    """调 ``mcp.list_tools()``，兼容「已在事件循环内」与「循环外」两种上下文。

    为什么不自接 ``asyncio.run``：审批有可能在 async 路径下被调（
    ``request_approval`` 本身是 async），那时 ``asyncio.run`` 会抛
    ``RuntimeError: asyncio.run() cannot be called from a running event loop``。
    早期版本把这个异常当「注解读不到」静默降级，导致 158 个读类工具全被
    判成「中级留痕」——静默失败比报错难查得多。这里分三种情况处理。
    为什么只在无循环时用单独线程：``list_tools`` 是同步完成的内存读取
    （读已注册的工具表），不碰网络，开线程只是为了避免嵌套循环。
    """
    coro_factory = mcp.list_tools
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    # 已在事件循环内：交给独立线程跑一个新循环，避免嵌套。
    import threading

    result: list[Any] = []
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            result.extend(asyncio.run(coro_factory()))
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=_runner, name="mcp-annotation-loader", daemon=True)
    thread.start()
    thread.join(timeout=10)
    if thread.is_alive():
        raise TimeoutError("读取 MCP 工具表超时（10s）")
    if error:
        # 有意捕获 BaseException：_runner 跑在独立线程里，asyncio 取消（
        # CancelledError 自 Python 3.8 起继承 BaseException）与 KeyboardInterrupt
        # 若不在这里接住，异常会死在子线程中丢失，join 后的调用方就分不清
        # 「子线程正常返回」与「子线程被中断」——前者会让审批静默退回名字判定，
        # 后者应原样上抛。故此处保留宽捕获，只负责把异常透传给主线程。
        raise error[0]
    return result


#: 注解表缓存（模块级懒加载一次）。
#: 注意：这里**不用 ``lru_cache``**——它会在并发首次调用时把「加载中/失败的
#: 空表」一起记下来，导致同进程内先后调用拿到不一致结果（实测：第一个工具
#: 拿到注解、后续全 ``None``）。审批是安全路径，宁可多读一次也不能读出两套答案。
#: 本模块的读写在函数内经 ``global`` 完成，CodeQL 会误报「未使用」，不可删除。
_ANNOTATION_TABLE: dict[str, dict[str, Any] | None] | None = None


def _reset_annotation_cache() -> None:
    """清缓存（供测试与热加载用）。

    为什么需要公开一个重置口：``mcp_server`` 的工具注册表在某些测试场景下会
    被重新导入/重建，旧快照就陈旧了。生产路径不会调它。
    """
    global _ANNOTATION_TABLE
    _ANNOTATION_TABLE = None


def _sync_tool_snapshot(mcp: Any) -> list[Any]:
    """同步读 ToolManager 里已注册的工具（注解表的**第二来源**）。

    ``mcp.list_tools()`` 在某些上下文里会给空（启动早期注册未完成、或事件循环
    状态异常），此时注解表会变成空表——而空表意味着 ``classify_risk`` 只剩名字
    黑名单，插件自报的 ``MCP_TOOL_RISK`` 被彻底无视。ToolManager 是进程内活的
    注册表，同步读它没有上下文依赖。
    """
    manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", None)
    if not isinstance(tools, dict):
        return []
    return list(tools.values())


def _annotation_table() -> dict[str, dict[str, Any] | None]:
    """工具短名 → MCP 注解字典（进程内懒加载一次，失败时返回空表）。

    ``mcp_server`` 是共享常驻进程，本进程（Django）导入它会多加载一份注册表。
    只在**首次需要时**读一次；加载失败不抛错——服务端二次判定退回纯名字
    黑名单，与改造前行为一致（不会因为注解表读不到就放行）。

    返回 ``None`` 表示该工具**没有声明**注解；空表（加载失败）与「全部未声明」
    由 ``load_tool_annotations`` 区分（空表时直接回 ``None``）。
    """
    global _ANNOTATION_TABLE
    if _ANNOTATION_TABLE is not None:
        return _ANNOTATION_TABLE
    try:
        from mcp_server.server import mcp

        tools = _list_mcp_tools(mcp)
        if not tools:
            # 见 `_sync_tool_snapshot` 的说明：list_tools 给空时退回注册表。
            tools = _sync_tool_snapshot(mcp)
    except Exception as exc:
        logger.warning("读取 MCP 工具注解失败，审批退回纯名字判定: %s", exc)
        _ANNOTATION_TABLE = {}
        return _ANNOTATION_TABLE
    table: dict[str, dict[str, Any] | None] = {}
    for tool in tools:
        hints = getattr(tool, "annotations", None)
        if hints is None:
            table[tool.name] = None
            continue
        table[tool.name] = {
            "read_only_hint": getattr(hints, "read_only_hint", None),
            "destructive_hint": getattr(hints, "destructive_hint", None),
            "open_world_hint": getattr(hints, "open_world_hint", None),
        }
    if not table:
        # **空表绝不落缓存**：这与本模块不用 ``lru_cache`` 是同一条理由——
        # 启动早期 ``list_tools`` 与注册表都还可能是空的，一旦把空表记下来，
        # 整个进程生命周期内审批分级都只剩名字黑名单，插件的风险声明被静默丢弃。
        # 真实症状：`weike_advanced_search` 自报 write，却一直判 LOW（无审批、无留痕）。
        logger.warning("MCP 注解表为空，本次不缓存（下次调用重试）；审批暂时退回纯名字判定")
        return table
    _ANNOTATION_TABLE = table
    return table


def prime_annotation_cache(table: dict[str, dict[str, Any] | None]) -> int:
    """用外部已读到的表**预热**缓存（MCP 进程内唯一正确的读法）。

    为什么需要它：MCP 进程里 ``mcp.list_tools()`` 是 async 且依赖请求上下文，
    在启动期调会抛错 → 本模块退回空表 → 整条审批分级只剩名字黑名单（实测
    2026-11-21 生产日志「注解 0 条」）。MCP 进程自己有活的 ``ToolManager``，
    同步读它才是准的；读到的表交给这里，两个进程（MCP / Django）口径一致。
    """
    global _ANNOTATION_TABLE
    _ANNOTATION_TABLE = dict(table)
    return len(_ANNOTATION_TABLE)


def _registered_now(short_name: str) -> bool:
    """该工具此刻是否真的在 MCP 注册表里（用于判断缓存是否陈旧）。"""
    try:
        from mcp_server.server import mcp
    except ImportError:
        # 只接「导入期失败」：`mcp_server` 未安装/被裁剪的环境里本模块仍需可用。
        # 其余异常照常抛——吞掉 AttributeError 会把「注册表结构变了」伪装成「工具不在」，
        # 而那个方向只会让审批更松。
        return False
    return any(getattr(tool, "name", None) == short_name for tool in _sync_tool_snapshot(mcp))


def load_tool_annotations(tool_name: str) -> dict[str, Any] | None:
    """按工具全名/短名取 MCP 注解（取不到返回 ``None``）。

    **命中不了就重建一次**：注解表可能在内置工具注册完、**插件工具还没注册**的那一刻
    就被建好并缓存；之后插件再注册（``MCP_TOOL_RISK`` 声明随之带注解进来），缓存却不会
    自愈——查不到就退回名字判定，插件自报的风险等级被静默丢弃（真实症状：
    ``weike_advanced_search`` 声明 write 却被判 LOW，无审批也无留痕）。

    只在「缓存里没有 **且** 注册表里确实有」时重建，所以正常路径只多一次 dict 查找；
    重建是进程内的，不碰网络。
    """
    short_name = tool_name[len(MCP_TOOL_PREFIX) :] if tool_name.startswith(MCP_TOOL_PREFIX) else tool_name
    table = _annotation_table()
    if not table:
        return None
    entry = table.get(short_name)
    if entry is not None:
        return entry
    if not _registered_now(short_name):
        return None
    _reset_annotation_cache()
    return _annotation_table().get(short_name)
