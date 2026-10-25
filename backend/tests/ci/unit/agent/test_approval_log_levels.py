"""审批链路日志级别门禁:except 内 debug 吞错在 approval.py 清零。

背景(2026-10-25 三十三轮 agent 运行时审计):根 CLAUDE.md 的标准——
「如果这次失败会让用户看到一个无法解释的结果,它就是 warning 以上」。
approval.py 是审批链路权威:三处 ``except Exception + logger.debug``
全是会让用户看到无法解释结果的失败(审批决定跨 worker 丢失→
「审批了但工具没执行」;waiter 心跳丢失→离线挂起判定失真;查会话
失败→审批记录丢会话关联)。已全部升 warning,本门禁防回退。

event_bus 的 debug 降级(实时投递不受影响的 Redis 回放/中继)是
「预期内且高频、且有降级分支正常走」的合法 debug,不受本门禁约束。
"""

from __future__ import annotations

import ast
from pathlib import Path

_APPROVAL_PY = Path(__file__).resolve().parents[4] / "apps" / "agent" / "services" / "approval.py"


def test_approval_has_no_debug_swallowed_exceptions() -> None:
    source = _APPROVAL_PY.read_text(encoding="utf-8")
    tree = ast.parse(source)
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
    assert not offenders, (
        "approval.py 审批链路在 except 内用 logger.debug 吞错(根 CLAUDE.md 标准:"
        "失败若让用户看到无法解释结果必须 ≥ warning)——行号: "
        + str(offenders)
    )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
