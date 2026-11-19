"""防复发：``verify_dsh_mcp`` 不得从 SSE 里断言一个生产已经静默的事件类型。

## 这条测试要挡的是哪个真回归

commit e56b6bb5 把 ``request/header`` 加进 ``dsh_backend._SILENT_EVENT_TYPES``
（一次合法的带宽优化：该事件对前端没有意义），而
``backend/scripts/verify_dsh_mcp.py``（现已在仓库根的 ``scripts/`` 下）当时**唯一**的判定就是从
``async for frame in backend.stream(ctx)`` 的 SSE 帧里取 ``request/header``。
结果：仓库唯一的 dsh 工具面端到端验收手段直接失效（实测
``FAIL: 没有收到 request/header 事件``），而生产其实完全正常。

根因不是「静默错了」，而是「验证依赖了被测系统的输出过滤」。不变量是：

    **断言的数据源必须位于过滤层之前**

脚本现在从 ``_NotificationBridge.put``（SDK 回调链，``_translate`` 之前）采集，
并把这份依赖写进 :data:`_ASSERTION_SOURCE_EVENT_TYPES`；断言若又改成从 SSE 取，
则必须登记进 :data:`_SSE_ASSERTION_SOURCE_EVENT_TYPES`。本文件的三条断言：

1. 依赖声明非空且含 ``request/header``——否则后面两条会退化成永真；
2. 从 SSE 断言的事件类型 ∩ 生产静默类型 == 空集（e56b6bb5 的回归形态）；
3. 第 2 条的结果同时与依赖声明对得上：断言依赖的类型必须**不是**被静默的，
   或者脚本必须已被显式登记为「不再从 SSE 取」（即它不出现在 SSE 依赖集合里）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from apps.agent.backends import dsh_backend

#: 脚本在**仓库根**的 ``scripts/``（不是 ``backend/scripts/``——后者被 gitignore，
#: 验收交付物不该待在那里，见 changelog v27.9.6）。
#: ``parents[4]`` 是 ``backend/``，再上一级才是仓库根。
_SCRIPT_PATH = Path(__file__).resolve().parents[5] / "scripts" / "verify_dsh_mcp.py"

#: 脚本里会被 ``event.get("type")`` 读到的 dsh 事件类型全集。用来防止「有人新增
#: 一处读取却忘记登记」——那会让静默交集检查被绕过（空转通过）。
_KNOWN_EVENT_TYPE_LITERALS = frozenset(
    {
        "request/header",
        "request/context",
        "system/message",
        "turn/start",
        "turn/end",
        "step/start",
        "step/end",
        "agent/inbox/spliced",
        "user/message",
    }
)


def _load_verify_script() -> ModuleType:
    """按路径导入验证脚本。

    根 ``scripts/`` 不是包（没有 ``__init__.py``），也不在 ``pythonpath`` 上，
    所以只能按文件加载。脚本顶部的 ``django.setup()`` 与 sys.path 处理是幂等的，
    pytest 环境里已经设好 ``DJANGO_SETTINGS_MODULE``，重复执行无害。
    """
    spec = importlib.util.spec_from_file_location("_verify_dsh_mcp_under_test", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


@pytest.fixture(scope="module")
def verify_script() -> ModuleType:
    assert _SCRIPT_PATH.is_file(), f"找不到验证脚本：{_SCRIPT_PATH}"
    return _load_verify_script()


def test_script_declares_assertion_dependencies(verify_script: ModuleType) -> None:
    """依赖声明必须存在、非空，且包含工具注册的唯一证据 ``request/header``。"""
    declared = verify_script._ASSERTION_SOURCE_EVENT_TYPES
    assert isinstance(declared, frozenset)
    assert declared, "脚本必须声明它断言依赖的事件类型（否则本文件的检查失去对象）"
    assert "request/header" in declared, "工具注册的唯一证据来自 request/header"
    sse_declared = verify_script._SSE_ASSERTION_SOURCE_EVENT_TYPES
    assert isinstance(sse_declared, frozenset)
    assert not sse_declared, (
        "脚本当前所有断言都从过滤前的通知采集（_capture_notifications），"
        "以 SSE 帧为断言来源的登记应为空；若确实要从 SSE 断言，先确认该类型不被静默。"
    )


def test_sse_assertion_sources_are_not_silenced_by_production(verify_script: ModuleType) -> None:
    """核心不变量：从 SSE 断言的事件类型 ∩ 生产静默类型 == 空集。

    e56b6bb5 的回归正是「交集非空且脚本仍从 SSE 取」——这条断言让它在 CI 里
    立刻红，而不是等到有人手跑脚本才发现验收手段已死。
    """
    overlap = set(verify_script._SSE_ASSERTION_SOURCE_EVENT_TYPES) & set(dsh_backend._SILENT_EVENT_TYPES)
    assert not overlap, (
        f"这些事件类型被 dsh_backend._SILENT_EVENT_TYPES 静默（不会进 SSE），"
        f"但 verify_dsh_mcp 仍从 SSE 把它们当断言依据：{sorted(overlap)}。\n"
        f"修法：把断言的数据源改成过滤层之前（见脚本的 _capture_notifications），"
        f"而不是把它们从静默白名单里去掉——那是把带宽优化退回去。"
    )


def test_assertion_dependencies_are_delivered_by_their_declared_source(verify_script: ModuleType) -> None:
    """依赖声明的两种来源必须自洽：要么不进静默、要么不被当成 SSE 来源。

    这是把「断言依赖」与「数据源」钉在一起的那颗钉：某个类型出现在
    ``_ASSERTION_SOURCE_EVENT_TYPES`` 里，就说明脚本需要它；如果生产把它静默了
    （它到不了 SSE），那脚本只能从过滤前采集——也就是它**不能**同时出现在 SSE
    依赖集合里（由上面两条守住）。这里顺带断言脚本确实从过滤前采集。
    """
    silenced = set(dsh_backend._SILENT_EVENT_TYPES)
    misplaced = {
        event_type
        for event_type in verify_script._ASSERTION_SOURCE_EVENT_TYPES & silenced
        if event_type in verify_script._SSE_ASSERTION_SOURCE_EVENT_TYPES
    }
    assert not misplaced, (
        f"这些类型既被生产静默又被声明为 SSE 断言来源：{sorted(misplaced)}；"
        f"它们永远不会出现在 backend.stream() 的输出里。"
    )
    # 采集点必须在过滤层之前：脚本应包 _NotificationBridge.put（_translate 之前
    # 的唯一统一入口），而不是只攒 frames。字符串级检查足够——导入期不执行任何
    # dsh 逻辑，跑一遍验证脚本会起真子进程，不适合放进 CI 单测。
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "_NotificationBridge" in source and "from apps.agent.backends.dsh_backend import" in source, (
        "脚本必须从 _NotificationBridge（过滤层之前）采集通知"
    )
    assert "async for frame in backend.stream(ctx)" in source, (
        "backend.stream 仍要跑：它才是驱动 dsh 的入口（事件只用于排障抄录）"
    )


def test_no_unregistered_event_type_reads(verify_script: ModuleType) -> None:
    """脚本源码里读取的事件类型字面量必须已登记，且全部有据可查。

    只查交集还不够：有人新增一处 ``event.get("type") == "xxx"`` 却忘了登记，
    交集检查照样通过，那次回归又没人挡。
    """
    read_types = {
        literal for literal in _KNOWN_EVENT_TYPE_LITERALS if f'"{literal}"' in _SCRIPT_PATH.read_text(encoding="utf-8")
    }
    undeclared = read_types - set(verify_script._ASSERTION_SOURCE_EVENT_TYPES)
    assert not undeclared, (
        f"脚本出现这些事件类型字面量但没登记到 _ASSERTION_SOURCE_EVENT_TYPES：{sorted(undeclared)}；"
        f"不登记就绕过了静默交集检查。"
    )
