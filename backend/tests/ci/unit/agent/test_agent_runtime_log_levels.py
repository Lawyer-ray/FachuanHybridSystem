"""agent 运行时：except 内 debug 吞错门禁（approval + live_sessions + question）。

背景（根 CLAUDE.md 标准）：**如果这次失败会让用户看到一个无法解释的结果，
它就是 warning 以上**。只有「预期内且高频、且有降级分支正常走」才配 debug。

`test_approval_log_levels.py` 只钉死了 approval.py。审计第 6 轮发现
live_sessions（会话路由表）与 question（提问答案键）是同一类问题——
前者表现为「插话没生效」，后者表现为「同一问题被重复作答/串答案」，
都是用户可见的无法解释结果，因此同口径纳入门禁。

event_bus 的 debug 降级（实时投递不受影响的 Redis 回放/中继）属合法降级，
不在本门禁范围。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_AGENT_SERVICES = Path(__file__).resolve().parents[4] / "apps" / "agent" / "services"

# 这些文件的 except 分支失败会直接呈现为「用户看到无法解释的结果」
_GUARDED = ["approval.py", "live_sessions.py", "question.py"]


def _debug_calls_in_except(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "debug"
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "logger"
            ):
                offenders.append(sub.lineno)
    return offenders


@pytest.mark.parametrize("filename", _GUARDED)
def test_no_debug_swallowed_exceptions(filename: str) -> None:
    path = _AGENT_SERVICES / filename
    assert path.exists(), f"门禁文件缺失，路径可能已变动: {path}"
    offenders = _debug_calls_in_except(path)
    assert not offenders, (
        f"{filename} 在 except 内用 logger.debug 吞错（根 CLAUDE.md 标准："
        f"失败若让用户看到无法解释结果必须 ≥ warning）——行号: {offenders}"
    )
