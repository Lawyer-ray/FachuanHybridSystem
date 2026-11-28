"""试跑**真机**验收：真起一个 pi 子进程 + 真连共享 MCP，跑一轮看模型是否照做。

默认跳过（CI 不具备 pi 运行时与共享 MCP，也不该为一次按钮点花掉模型额度）。
手动跑法：

```bash
cd backend
FACHUAN_SKILL_TRIAL_LIVE=1 DB_NAME=test_fachuan_dev PYTHONPATH=. \
  .venv/bin/python -m pytest tests/ci/unit/agent/test_skill_trial_live.py -s
```

它验的是静态用例**永远验不出**的三件事：

1. `--append-system-prompt` 里的注入块真的到达了模型（不是被 pi 丢掉、也不是被当成
   文件路径去读）；
2. 模型**照做了**（回显暗号），而不是凭常识编一个听起来合理的答案；
3. 隔离运行真的不写会话历史、工具面真的是只读。

**它不能证明的东西**（别误读成「上线一定没问题」）：待审技能还不在
`resolve_for_user` 的交付面里，所以试跑是把正文**内联**进去的——「模型会不会在合适
场景自己想到去读这条技能」这一层，要靠已发布技能在日常使用中持续验证。
"""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

import pytest

from apps.agent.models import AgentMessage
from apps.agent.services.skills import trial
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret
MARKER = "MANGO-TRIAL-9147"

LIVE = os.environ.get("FACHUAN_SKILL_TRIAL_LIVE", "").strip() in {"1", "true", "yes"}


def _pi_available() -> bool:
    from apps.agent.pi.rpc_client import resolve_pi_bin

    try:
        return bool(shutil.which(resolve_pi_bin()))
    except (OSError, ValueError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(not LIVE, reason="真机验收：设 FACHUAN_SKILL_TRIAL_LIVE=1 才跑（需 pi + 共享 MCP）"),
]


@pytest.mark.django_db(transaction=True)
def test_live_trial_echoes_marker(firm_row: Any = None) -> None:
    if not _pi_available():
        pytest.skip("找不到 pi 可执行文件")

    firm = LawFirm.objects.create(name="真机试跑所")
    lawyer = Lawyer.objects.create_user(username="live-trial", password=TEST_PASSWORD, law_firm=firm)
    from apps.agent.models import AgentSkill

    skill = AgentSkill.objects.create(
        scope=AgentSkill.Scope.LAWYER,
        lawyer=lawyer,
        name="live-trial-skill",
        title="真机试跑技能",
        description="用于真机验收的试跑技能",
        body=f"## 回答格式\n无论用户问什么，回答的第一行必须原样输出：{MARKER}",
        status=AgentSkill.Status.ACTIVE,
        created_by=lawyer,
    )

    before = AgentMessage.objects.count()
    result = asyncio.run(trial.run_trial(user_id=lawyer.pk, key=f"skill:{skill.pk}"))
    after = AgentMessage.objects.count()

    print("\n===== 试跑回执 =====")  # noqa: T201 - 真机验收脚本，输出要人看
    print(f"ok={result.ok} backend={result.backend} model={result.model} ms={result.duration_ms}")  # noqa: T201
    print(f"tool_calls={result.tool_calls}")  # noqa: T201
    print(f"error={result.error!r}")  # noqa: T201
    print("----- 模型回复（前 600 字）-----")  # noqa: T201
    print(result.text[:600])  # noqa: T201
    print("----- 会话历史条数 before/after:", before, after)  # noqa: T201

    assert result.ok, f"试跑失败：{result.error}"
    assert MARKER in result.text, f"模型没有照做（暗号未出现）\n实际回复：{result.text[:400]}"
    assert after == before, "试跑不许写会话历史"


@pytest.mark.django_db(transaction=True)
def test_live_trial_of_pending_firm_skill() -> None:
    """真机的**真实用途**：审批人试跑一条待审的所内技能。

    这条比个人技能那条更关键——待审技能**不在** ``resolve_for_user`` 的交付面里，
    所以它验的正是「内联工作区正文」这条路在共享作用域下也成立（来源声明、scope
    标签、渲染都按所内走），而不是只对个人技能碰巧有效。
    """
    if not _pi_available():
        pytest.skip("找不到 pi 可执行文件")

    from apps.agent.models import AgentSkill

    firm = LawFirm.objects.create(name="真机待审所")
    admin = Lawyer.objects.create_user(
        username="live-trial-admin", password=TEST_PASSWORD, law_firm=firm, is_admin=True
    )
    skill = AgentSkill.objects.create(
        scope=AgentSkill.Scope.LAW_FIRM,
        law_firm=firm,
        name="live-firm-draft",
        title="真机待审所内技能",
        description="待审状态下试跑",
        body=f"## 全所格式\n每条回答的第一行必须是：{MARKER}-FIRM",
        status=AgentSkill.Status.DRAFT,
        review_status=AgentSkill.ReviewStatus.PENDING,
        created_by=admin,
    )

    # 待审 = 不在交付面（这正是双轨发布的意义）
    from apps.agent.services.skills import resolve

    assert "live-firm-draft" not in [item["name"] for item in resolve.resolve_for_user(admin.pk)]

    result = asyncio.run(trial.run_trial(user_id=admin.pk, key=f"skill:{skill.pk}"))

    print("\n===== 待审所内技能试跑 =====")  # noqa: T201
    print(f"ok={result.ok} scope={result.skill['scope']} ms={result.duration_ms}")  # noqa: T201
    print("----- 回复（前 400 字）-----")  # noqa: T201
    print(result.text[:400])  # noqa: T201

    assert result.ok, f"试跑失败：{result.error}"
    assert result.skill["scope"] == "law_firm"
    assert "全所统一规范" in result.injected, "所内技能必须用所内的来源声明"
    assert f"{MARKER}-FIRM" in result.text, f"模型没有照做：{result.text[:300]}"
