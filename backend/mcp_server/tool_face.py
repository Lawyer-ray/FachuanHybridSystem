"""工具面指纹 —— 「这份代码值不值得重启共享 MCP」的判据。

## 指纹是什么

把当前注册的每个工具的 ``name`` + ``description`` + ``inputSchema`` +
``annotations`` 归一化成规范 JSON，按 name 排序后拼接，取 sha256 的前 12 位。同一份
代码算出的指纹恒定；工具增删、改描述、改参数 schema、改注解都会换指纹。

## 它不是什么

**这不是线上协议契约**：不做版本协商、不保证跨仓库/跨版本稳定（换一次规范化
写法，指纹就整体换掉，这是可接受的——它只跟"这两份进程是不是同一份工具面"
有关）。它唯一回答的问题是「重启共享 MCP 值不值得」：共享 MCP 的工具注册表是
**进程启动时快照**，改了代码不重启，模型拿到的还是旧工具面且**没有任何报错**
（只表现为「没有这个工具」）。过去这件事只能靠人的记忆，现在是一次字符串比较
（``scripts/shared_mcp.sh --if-stale`` / ``bluegreen``）。

**描述也算「变了」**：``description`` 是模型选工具的主要依据，改一段描述等于改
模型行为，和新增工具一样值得重启；``inputSchema`` 同理——参数名/描述/enum 都是
模型构造调用时的输入。

**注解也算「变了」**：``annotations`` 是**审批分级的输入**（``read_only_hint`` /
``destructive_hint`` 直接决定风险等级），改它等于改「什么工具会被拦下来」。插件把
工具风险从 ``read`` 调到 ``high`` 时往往**只动注解**——名字、描述、schema 一个字都
不改；指纹里不含注解，``--if-stale`` 就会静默跳过，常驻进程继续按旧的低风险放行
（安全侧漏判）。

## 两个入口

- :func:`tool_face_fingerprint` —— 纯函数，只吃四字段的工具表，不碰 Django/网络；
- :func:`tool_face_from_mcp` —— 从活的 MCP 实例读工具表，供 ``python -m
  mcp_server`` 的启动日志与 ``shared_mcp.sh verify`` 用同一个口径。

``python -m mcp_server.tool_face`` 打印**代码侧（离线）**指纹：shell 侧拿它跟线上
握手算出的指纹比对，相同就跳过重启。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from collections.abc import Iterable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

#: 指纹长度：12 位十六进制 = 48 bit。几百个工具的量级碰撞概率可忽略，
#: 又能在一行日志/一张终端里读完。
FINGERPRINT_HEX_CHARS = 12


def _canonical_json(value: Any) -> str:
    """规范 JSON：键排序 + 无多余空白 + 保留中文原文。

    ``ensure_ascii=False`` 不是风格问题：转义会把同一段中文变成两种字节序列
    （``\\u4e2d`` 与原文），指纹就取决于「谁先写进仓库」而不是内容。
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _normalize_annotations(value: Any) -> dict[str, Any]:
    """把任意形态的注解归一成「不含 None 值」的普通 dict。

    为什么必须丢掉值为 ``None`` 的键：协议注解全是可选的（``read_only_hint`` /
    ``destructive_hint`` / ``open_world_hint`` / ``title``），pydantic 的
    ``model_dump()`` 会把没写的字段也 dump 成 ``None``。若保留，同一份代码从对象侧
    读到的 ``{"read_only_hint": None}`` 与从 wire 侧读到的「压根没这个键」就会算成
    两个指纹——``--if-stale`` 退化成每次都真重启，门禁又回到「靠人记」。

    Mapping 原样（只做去 None 的浅拷贝）：JSON 解析出来的注解已经是扁平字典，再按
    字段名重排会把「插件自报的未知扩展字段」丢掉，那同样属于审批分级的输入。
    """
    if value is None:
        return {}
    if isinstance(value, Mapping):
        raw: dict[str, Any] = dict(value)
    else:
        dump = getattr(value, "model_dump", None)
        if not callable(dump):
            return {}
        raw = dump(exclude_none=True)
    return {str(key): item for key, item in raw.items() if item is not None}


def tool_face_entries(tools: Iterable[Any]) -> list[dict[str, Any]]:
    """把任意形态的工具表统一成「只含指纹关心的四字段」的 dict 列表。

    为什么要统一：同一次切换里工具表会出现三种形态——wire dict（``inputSchema``
    驼峰）、pydantic ``Tool``（``input_schema`` 下划线）、``ToolManager`` 里的注册
    对象。指纹**必须跨这三种形态恒等**，否则 verify 拿 wire 侧、注册表拿对象侧，
    就会把「同一份代码」误判成漂移（假红 → ``--if-stale`` 每次都真重启）。

    schema 取值要带 ``parameters`` 兜底：SDK 内部注册对象的字段名不是 ``input_schema``
    而是 ``parameters``（``mcp/server/mcpserver/tools/base.py::Tool``），只用
    ``input_schema`` 会让 ``_sync_tool_snapshot`` 退回路径下的每个工具都变成
    ``inputSchema={}``——指纹照样是个合法字符串，却对 schema 改动完全失明。

    ``annotations`` 是**审批分级的输入**，改了它必须换指纹（见模块 docstring）。
    """
    entries: list[dict[str, Any]] = []
    for tool in tools:
        if isinstance(tool, Mapping):
            name = tool.get("name")
            description = tool.get("description")
            schema = tool.get("inputSchema") or tool.get("input_schema")
            annotations = tool.get("annotations")
        else:
            name = getattr(tool, "name", None)
            description = getattr(tool, "description", None)
            schema = getattr(tool, "input_schema", None) or getattr(tool, "parameters", None)
            annotations = getattr(tool, "annotations", None)
        entries.append(
            {
                "name": str(name or ""),
                "description": str(description or ""),
                "inputSchema": schema if isinstance(schema, Mapping) else {},
                "annotations": _normalize_annotations(annotations),
            }
        )
    return entries


def tool_face_fingerprint(tools: Iterable[Any]) -> str:
    """算工具面指纹（同一份工具表恒等、与注册顺序无关）。

    ``tools`` 可以是 wire dict、pydantic ``Tool`` 或注册对象，口径见
    :func:`tool_face_entries`。
    """
    entries = sorted(tool_face_entries(tools), key=lambda entry: entry["name"])
    payload = "\n".join(_canonical_json(entry) for entry in entries)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:FINGERPRINT_HEX_CHARS]


def tool_face_from_mcp(mcp: Any) -> list[dict[str, Any]]:
    """从已注册的 MCP 实例读工具面（返回四字段 dict 列表）。

    「已在事件循环内 vs 循环外」这套判断**只复用一处实现**：
    ``apps/agent/services/approval/annotations.py::_list_mcp_tools``。那里记着踩过
    的坑——async 路径里直接 ``asyncio.run`` 会抛 ``RuntimeError``，早期被静默降级
    成「读不到工具」，结果整条审批分级只剩名字黑名单。这里不另写一套：两套并存
    的话，蓝绿切换的工具面与审批读到的工具面会各说一套。

    ``list_tools`` 抛错或给空时退回 ``ToolManager`` 的同步注册表（同模块第二来源）：
    MCP 进程启动早期 ``list_tools`` 可能还不能用，而启动日志里的指纹必须是**真实
    工具面**——空表指纹看起来同样是个合法字符串，等于把「没读到」伪装成「工具面为空」。
    """
    from apps.agent.services.approval.annotations import _list_mcp_tools, _sync_tool_snapshot

    try:
        tools = _list_mcp_tools(mcp)
    except (RuntimeError, TimeoutError, ValueError, TypeError, AttributeError, OSError) as exc:
        # 读不到工具表不该让进程起不来：退回同步注册表。
        # 为什么不是 ``except Exception``：仓规 ``forbid-new-broad-except`` 是全仓棘轮
        # （只许下调）。这里列出的是这条路径**已知**会抛的类型——事件循环里误用
        # ``asyncio.run``（RuntimeError）、``annotations._list_mcp_tools`` 自己的
        # join 超时（TimeoutError）、SDK 的 pydantic 校验（ValueError/TypeError）、
        # 注册对象缺字段（AttributeError）、socket/线程（OSError）。
        # 其余异常应当冒泡：那说明工具表本身坏了，静默退回只会把问题藏起来。
        logger.warning("list_tools 读工具表失败，退回 ToolManager 同步注册表: %s", exc)
        tools = []
    if not tools:
        tools = _sync_tool_snapshot(mcp)
    return tool_face_entries(tools)


def _offline_fingerprint() -> str:
    """算当前代码（离线）指纹。**必须在 ``django.setup()`` 之后调用**。

    ``mcp_server.server`` 的工具模块在导入期就访问 Django 模型，早于 setup 会抛
    ``AppRegistryNotReady``（与 ``mcp_server/__main__.py`` 同一条约束）。
    """
    from mcp_server.server import mcp

    return tool_face_fingerprint(tool_face_from_mcp(mcp))


if __name__ == "__main__":
    # 复用入口模块的引导：sys.path、DJANGO_SETTINGS_MODULE、bootstrap 期 stdout
    # 改道只有那一份实现，本命令不该有第二份。
    from mcp_server.__main__ import _bootstrap_django

    _bootstrap_django()

    # 导入工具模块的窗口同样把 stdout 改道 stderr：几百个工具模块里任何一个在 import
    # 期 print 都会插进本命令唯一的输出行（与 ``__main__`` 的 stdio 分支同一条理由）。
    _real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        _fingerprint = _offline_fingerprint()
    finally:
        sys.stdout = _real_stdout
    # 用 sys.stdout.write 而不是 print()：仓规 ``forbid-added-print`` 禁止新增 print
    # （防止调试残留混进 stdio 协议通道）。而本命令的**存在意义**就是向 stdout 吐一行
    # 指纹给 shell 抓，所以它是"协议输出"而不是日志，logger 不能替代。
    sys.stdout.write(f"{_fingerprint}\n")
