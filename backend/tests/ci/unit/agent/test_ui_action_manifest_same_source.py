"""UI 动作清单同源守卫（08 §10 的门禁 G1）。

为什么需要它：清单是双端契约，而契约漂移的**表现是静默的**——

- 后端加了动作、前端没有执行器 → 模型调完页面毫无反应，日志里连错误都没有；
- 前端手抄一份「看起来对」的清单 → 漂移在重生成时才被发现，而重生成只是把模板再抄一遍，
  漂移一条不少（``sse_types.py`` 历史上就是这样三源并存）。

所以本文件只认一条事实：``python -m apps.agent.services.ui_action --ts`` 的输出与仓库里的
``frontend/src/features/copilot/ui-tools/generated.ts`` **逐字节相等**。手改生成物、
改了 ``manifest.py`` 忘了重生成，两种错都会在这里红。

**不建库**（无 ``django_db``）：生成器只 import ``manifest``（纯数据），它与 Django 无关——
这正是它能跑在「没有 settings 的 CI 生成阶段」的前提（``services/__init__.py`` 的懒别名
就是为它改的），所以顺带钉住「生成器不拖 Django」这条约束。

与前端门禁的分工（G2 在那边）：本文件守「同一份字节」，``registry.node.test.ts`` 守
「同一组名字」（每个 ``UiToolName`` 都有执行器、执行器表没有多余项、每条 schema 都有
非法样例被拒）。两条一起才叫双端完备，缺一条都只算一半。
"""

from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

import pytest

from apps.agent.services.ui_action.__main__ import generate_ts
from apps.agent.services.ui_action.manifest import UI_ACTIONS

#: 仓库内生成物的位置（本文件在 backend/tests/ci/unit/agent/，上推 5 层到仓库根）
_TS_PATH = (
    Path(__file__).resolve().parents[5] / "frontend" / "src" / "features" / "copilot" / "ui-tools" / "generated.ts"
)


def test_ts_matches_checked_in_file() -> None:
    """生成物必须与仓库里的 `generated.ts` 逐字节一致。

    失败时的修法只有一条：改 `manifest.py` 后重跑
    `python -m apps.agent.services.ui_action --ts > frontend/src/features/copilot/ui-tools/generated.ts`。
    **不要**手改生成物，也不要为了让断言变绿去改断言。
    """
    assert _TS_PATH.exists(), f"找不到清单生成物：{_TS_PATH}"

    generated = generate_ts()
    checked_in = _TS_PATH.read_text(encoding="utf-8")

    if generated != checked_in:
        diff = "\n".join(
            difflib.unified_diff(
                checked_in.splitlines(),
                generated.splitlines(),
                fromfile="仓库里的 ui-tools/generated.ts",
                tofile="由 manifest.py 生成的结果",
                lineterm="",
            )
        )
        pytest.fail(
            "UI 动作清单与生成物不一致（改了 manifest.py 却没重生成，或手改了生成物？）。\n"
            "修法：python -m apps.agent.services.ui_action --ts > "
            "frontend/src/features/copilot/ui-tools/generated.ts\n\n" + diff
        )


def test_generator_is_deterministic() -> None:
    """连跑两次必须逐字节相同。

    生成器里任何一处依赖 dict 书写顺序 / set 迭代序 / 时间，都会让同源测试随机红，
    而随机红的门禁最后一定会被绕过——所以确定性单独钉一条。
    """
    assert generate_ts() == generate_ts()


def test_generator_covers_every_action() -> None:
    """清单里每条动作都要在生成物里出现，且字段齐全。

    逐字节比对已经覆盖了「内容对不对」，这条管的是「下一次改动别把整段产出去掉」：
    例如 `_ts_spec` 只拼 name/risk/argsSchema 时，前端执行层缺 `describe` / `tier` /
    `undo` 就编译不过，而报错位置会指向生成物、不是真源。
    """
    ts = generate_ts()
    for action in UI_ACTIONS:
        assert f"name: '{action.name}'" in ts, f"生成物里缺少动作 {action.name}"
        for field in ("title", "describe", "argsSchema", "route", "risk", "tier", "handler", "idempotent", "undo"):
            assert f"{field}:" in ts, f"{action.name} 的生成结果缺少字段 {field}"
    assert "export const UI_TOOL_BY_NAME" in ts, "生成物缺少名字索引 UI_TOOL_BY_NAME（前端执行分派要用）"


def test_generator_runs_as_module_without_django_settings() -> None:
    """`python -m` 那条命令本身要能跑通（生成物与 CI 用的是同一条路径）。

    这条不是重复：import 视图（``generate_ts()``）走的是已加载的包，而 ``-m`` 还要
    先 import 父包 ``apps.agent.services``。历史上那里急切 import 了 Django 模型，
    于是生成器在没有 ``django.setup()`` 的进程里直接 ``AppRegistryNotReady``——报错位置
    指向 Django 模型、不是真凶（修法见 ``apps/agent/services/__init__.py`` 的懒别名）。
    """
    backend_dir = Path(__file__).resolve().parents[4]
    result = subprocess.run(
        [sys.executable, "-m", "apps.agent.services.ui_action", "--ts"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"生成器跑不起来：\n{result.stderr}"
    assert result.stdout == generate_ts(), "`-m` 的输出与 generate_ts() 不一致（两条路径不该各产一份）"
