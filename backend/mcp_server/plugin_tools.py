"""插件自带 MCP 工具：**有插件 dir 就有工具，没有就没有**。

## 为什么需要这一层

``mcp_server/server.py`` 里的 409 个工具是一条**硬编码 import 清单**：想多一个
工具，必须改主仓代码。而 ``backend/plugins/`` 是**独立版本控制**（子模块 + 私有
目录），插件自带的能力（威科私有 API、法院自动化、OCR…）只能被 app 层调用，
变不成模型能直接调的工具。

本模块给插件一条**约定式**出口：在插件目录里放 ``mcp_tools.py``，它的工具就自动
出现在 ``tools/list`` 里；没放就什么都不发生。

## 三条硬约束

1. **主仓不许出现任何私有插件名**。所以这里靠**目录扫描**发现，不靠注册表登记。
   ``git hooks`` 里那条「Forbid committing weike private implementation paths」
   正是为什么不能写成 ``PLUGINS = ["weike_api_private", ...]``。
2. **一个坏插件不能拖垮整个 MCP**。import 失败 / 契约不合法 → 记 warning 并跳过，
   其余工具照常。MCP 起不来等于全所 AI 功能停摆，代价远大于少几个工具。
3. **不可用时连名字都不出现**。用户要的是「没插件 = 没有这个工具」，不是
   「有工具但一调就报错」——后者会让模型反复重试一个永远失败的路径。

## 插件侧契约（``plugins/<name>/mcp_tools.py``）

```python
from typing import Annotated
from pydantic import Field

def search_private_cases(
    keyword: Annotated[str, Field(description="检索关键词")],
) -> dict:
    '''一句话说明这个工具做什么（会原样进 tools/list 的 description）。'''
    ...

#: 要暴露的工具列表（必填）。函数名即工具名，写进 MCP 后模型看到的就是它。
MCP_TOOLS = [search_private_cases]


def check_available() -> bool:
    '''可选：运行期可用性（缺凭据 / 服务不可达时返回 False）。'''
    return True
```

### 命名与分级（插件作者必须知道）

- **工具名不可与内置 409 个重名**：撞名直接跳过并告警（内置优先）。
- **注解自动推导**：``_tool_annotations`` 按名字 + ``classify_risk`` 推
  readOnly / destructive，插件不用自己写；但**名字里带 ``delete_`` / ``submit_``
  这类前缀会被判高危并弹审批卡**——这是刻意的。
- **分层自动生效**：未登记进 ``DIRECT_TOOLS`` 的插件工具默认走 ``deferred``
  （``tool_search`` 按需加载），所以不会白占每轮的固定前缀。

## 关闭开关

``FACHUAN_PLUGIN_TOOLS=off`` → 一个插件工具都不注册（回滚用；与
``FACHUAN_MCP_TOOL_TIERS=off`` / ``FACHUAN_MCP_SHARED=0`` 同风格）。
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from collections.abc import Callable, Iterable
from types import ModuleType
from typing import Any

logger = logging.getLogger(__name__)

#: 绝不能被"容错"吞掉的控制流异常。插件容错只该覆盖"插件坏了"，
#: 不该覆盖"进程该退出"或"本次调用被取消"。
_NOT_OURS: tuple[type[BaseException], ...] = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
)

#: 关闭开关（默认开启）。
ENABLED_ENV = "FACHUAN_PLUGIN_TOOLS"

#: 插件侧必须提供的入口文件名。
ENTRY_MODULE = "mcp_tools"

#: 插件侧导出名：要暴露的函数列表。
EXPORTS_ATTR = "MCP_TOOLS"


def enabled() -> bool:
    """插件工具总开关（解析口径与 ``toolface.shared_enabled`` 一致）。"""
    raw = os.environ.get(ENABLED_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def plugins_root() -> str | None:
    """``plugins`` 包的目录；没装插件时返回 ``None``。

    用 ``importlib`` 解析而不是拼 ``Path(__file__).parents[1]``：MCP 既可能以
    ``python -m mcp_server``（cwd=``backend/``）启动，也可能被 pytest / 验收脚本
    以别的 cwd 导入。包解析对两者都成立，路径拼接只对前者成立。
    """
    try:
        spec = importlib.util.find_spec("plugins")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return next(iter(spec.submodule_search_locations), None)


def discover_entry_modules() -> list[str]:
    """扫出所有 ``plugins/<name>/mcp_tools.py`` 的模块路径（排序，稳定）。

    只认**目录**下的同名文件，不递归：插件自己的子目录不该被当成独立插件。
    ``_`` 开头的目录跳过（``__pycache__`` / 约定私有）。
    """
    root = plugins_root()
    if not root:
        return []
    from pathlib import Path

    base = Path(root)
    found: list[str] = []
    for child in sorted(base.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        if (child / f"{ENTRY_MODULE}.py").is_file():
            found.append(f"{base.name}.{child.name}.{ENTRY_MODULE}")
    return found


def _collect(module: ModuleType) -> list[Callable[..., Any]]:
    """从插件模块取工具列表，顺手校验契约（不合法就整块丢弃并告警）。"""
    raw = getattr(module, EXPORTS_ATTR, None)
    if raw is None:
        logger.warning(
            "插件 %s 未导出 %s，跳过（不是错误：插件可能只提供非工具能力）",
            module.__name__,
            EXPORTS_ATTR,
        )
        return []
    if not isinstance(raw, (list, tuple)):
        logger.warning("插件 %s 的 %s 必须是 list/tuple，实际 %s，整块跳过", module.__name__, EXPORTS_ATTR, type(raw))
        return []
    tools: list[Callable[..., Any]] = []
    for item in raw:
        if not callable(item):
            logger.warning("插件 %s 的 %s 含非可调用项 %r，跳过该项", module.__name__, EXPORTS_ATTR, item)
            continue
        name = getattr(item, "__name__", "")
        if not name or name.startswith("_"):
            logger.warning("插件 %s 的工具缺少公开函数名（%r），跳过", module.__name__, name)
            continue
        tools.append(item)
    return tools


def _availability_ok(module: ModuleType) -> bool:
    """调用插件可选的 ``check_available()``；不带这个钩子视为可用。

    **失败一律当不可用**：这里判断错方向的代价是「工具出现但一调就 500」，
    而模型会反复重试它。宁可少几个工具。
    """
    probe = getattr(module, "check_available", None)
    if probe is None:
        return True
    try:
        return bool(probe())
    except _NOT_OURS:
        raise
    except BaseException:
        # 用 ``BaseException`` + 显式放行上面三类控制流异常：插件作者写什么都可能
        # （连 ``SystemExit`` 都可能），而「坏钩子」不该让整个 MCP 起不来。不用
        # 宽泛 except 会撞仓库的棘轮门禁（见 test_exception_ratchet），故用 BaseException。
        logger.warning("插件 %s 的 check_available() 抛异常，按不可用处理", module.__name__, exc_info=True)
        return False


def register_plugin_tools(
    register_tool: Callable[[Callable[..., Any]], Any],
    *,
    reserved_names: Iterable[str] = (),
) -> list[str]:
    """把插件工具注册进 MCP；返回**实际注册成功的工具名**（排序）。

    Args:
        register_tool: 主仓的注册装饰器（``mcp_server.server._t``）。传函数而不是
            让本模块 import ``server``——``server`` 在 import 期就会注册 409 个工具，
            反向依赖会让「导入本模块」产生一次完整注册副作用。
        reserved_names: 内置工具名集合。插件工具与之撞名时**跳过插件侧**：
            内置工具是审计与审批口径的基准，不能被插件覆盖。

    Returns:
        注册成功的工具名。空列表 = 没有插件 / 全部不可用 / 总开关关闭——
        这三种情况调用方都只该打一行日志，不该报错。
    """
    if not enabled():
        logger.info("插件工具已关闭（%s），不注册任何插件工具", ENABLED_ENV)
        return []

    reserved = set(reserved_names)
    registered: list[str] = []
    for module_path in discover_entry_modules():
        try:
            module = importlib.import_module(module_path)
        except _NOT_OURS:
            raise
        except BaseException:
            # 少几个插件工具远好过整个 MCP 起不来：MCP 挂掉 = 全所 AI 功能停摆。
            # 插件依赖缺失 / 语法错 / 自身 import 期异常都在这里。
            logger.warning("插件工具模块 %s 导入失败，跳过该插件", module_path, exc_info=True)
            continue

        if not _availability_ok(module):
            logger.info("插件 %s 报告不可用（check_available=False），不注册其工具", module_path)
            continue

        for tool in _collect(module):
            name = tool.__name__
            if name in reserved:
                logger.warning("插件工具 %s 与内置工具重名，跳过插件侧（内置优先）", name)
                continue
            if name in registered:
                logger.warning("插件工具 %s 重复注册，跳过后出现的那个", name)
                continue
            register_tool(tool)
            registered.append(name)

    if registered:
        logger.info("插件工具已注册 %d 个: %s", len(registered), ", ".join(sorted(registered)))
    return sorted(registered)


__all__ = [
    "ENABLED_ENV",
    "ENTRY_MODULE",
    "EXPORTS_ATTR",
    "discover_entry_modules",
    "enabled",
    "plugins_root",
    "register_plugin_tools",
]
