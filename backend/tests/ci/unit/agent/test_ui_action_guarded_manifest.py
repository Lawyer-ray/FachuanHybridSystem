"""第一条 ``guarded`` 动作（删除材料包）的清单 / 注册 / 核实门禁。

## 为什么这条动作值得单独一个文件

三档风险里 ``guarded`` 长期是空转（清单里没有任何动作落在这一档），所以「这一档真的
接上了吗」在 CI 里从来没有被回答过。``ui_material_prep_delete_pack`` 是第一条：它**不可逆**
（删记录 + 附件物理文件），因此同时要求三件事，且**互不替代**：

1. **后端审批**：注册出去的 ``ToolAnnotations`` 必须带 ``destructiveHint=True``，否则
   ``risk.py::_classify_by_annotations`` 判不到 HIGH，审批闸门根本不会弹卡——而这条动作
   的名字不以 ``delete_`` 开头，工具层的 ``DIRECT_PATTERNS`` 也兜不住它；
2. **分层可见**：必须进 ``CONFIRM_ACTION_NAMES`` 且真实 exposure 是 ``direct``。藏进
   ``tool_search`` 只降低可见性、不降低风险（律师反而看不见 AI 有删除能力）；
3. **服务端核实**：页面报「删了」只是线索。``material_prep_absent`` 要回库查一眼——
   查不到才算删掉（``True``），还查得到必须判 ``False`` 并明确禁止说「已删除」，
   查询本身报错则 ``None``（「我没看」≠「我看了没变」）。

## 为什么核实用例走 ``run_verifier`` 而不是直接调核实器

``material_prep_absent`` 与 ``material_prep_status`` 一样**不自己 catch**（仓库禁止扩大
``except``）：异常 → ``verified=None`` 的兜底在 :func:`verify.run_verifier`。
所以「查询报错」这一档只能从 ``run_verifier`` 进去测，直接调核实器测到的是异常冒泡，
而那不是线上行为。

``django_db(transaction=True)`` 是必须的：这些用例走 async ORM，它在 asgiref 执行器连接上跑，
普通事务包裹下看不见用例里创建的行（同 ``test_ui_action_verify.py``）。
"""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

import pytest
from django.db import DatabaseError
from django.utils import timezone
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from apps.agent.services.ui_action import verify
from apps.agent.services.ui_action.manifest import CONFIRM_ACTION_NAMES, DIRECT_ACTION_NAMES, UI_ACTIONS, UiAction
from apps.message_hub.models import InboxMessage, MessageSource
from mcp_server.tool_tiers import build_tool_exposure
from mcp_server.tools.ui.register import _register_actions

#: 被守住的那条动作。清单被改名 / 误删时这里当场红成一句人话（而不是让整个文件
#: 卡在 ``StopIteration`` 或 ``None`` 的类型错误上——那两种红都不会告诉人「哪条动作没了」）。
_DELETE_CANDIDATES = [action for action in UI_ACTIONS if action.name == "ui_material_prep_delete_pack"]
assert len(_DELETE_CANDIDATES) == 1, (
    f"清单里应当恰好有一条 ui_material_prep_delete_pack，实际 {len(_DELETE_CANDIDATES)} 条"
)
DELETE: UiAction = _DELETE_CANDIDATES[0]


def _register_into_probe(actions: Sequence[UiAction]) -> dict[str, Any]:
    """把动作注册进一个空的 ``MCPServer``，返回 ``名字 → SDK 工具对象``。

    与 ``test_ui_tool_tiers.py::_register_into_probe`` 同一口径：判级只取决于注册出去的
    那份 ``ToolAnnotations``，所以这里不 import ``mcp_server.server``（那会连带注册 441 个
    工具，慢且有进程级副作用）。
    """
    probe = MCPServer("ui-tool-guarded-probe")

    def _register(tool: Any, *, annotations: ToolAnnotations | None = None) -> Any:
        return probe.tool(annotations=annotations)(tool)

    _register_actions(actions, _register, reserved_names=set())
    return {tool.name: tool for tool in asyncio.run(probe.list_tools())}


class TestManifestFields:
    """字段口径：这一档是 guarded，而不是被顺手写成了 confirm。"""

    def test_risk_is_guarded_and_irreversible(self) -> None:
        """``guarded`` 的三个前提：不可撤销、有 ``delete`` 副作用、非幂等。

        三处都要断言，因为它们各自驱动一条不同的链路：``risk`` 决定审批 + 前端二次确认，
        ``undo``/``side_effects`` 进审计与治理判定，``idempotent=False`` 决定前端**不许**
        自动重试（重试一次删除的代价是「删了两次」这种无法解释的回执）。
        """
        assert DELETE.risk == "guarded", "删除材料包必须是 guarded（不可逆），不能降成 confirm"
        assert DELETE.undo == "none"
        assert "delete" in DELETE.side_effects
        assert DELETE.idempotent is False
        assert DELETE.verify == "material_prep_absent", "页面说删了不算数：必须声明服务端核实器"

    def test_tier_is_direct(self) -> None:
        """``guarded`` 一律 direct：藏起来只降低可见性、不降低风险。"""
        assert DELETE.tier == "direct"
        assert DELETE.name in DIRECT_ACTION_NAMES

    def test_args_schema_requires_integer_pack_id(self) -> None:
        """参数只有一个必填的整数 ``packId``：多一个字段就多一处「模型自己编」的面。"""
        schema = DELETE.args_schema
        assert schema["required"] == ["packId"]
        assert schema["additionalProperties"] is False
        assert schema["properties"]["packId"]["type"] == "integer"
        assert schema["properties"]["packId"]["description"], "缺描述时模型只能猜该填什么"


class TestApprovalWiring:
    """审批 / 分层的接线：派生集合里必须有它，真实 exposure 必须是 direct。"""

    def test_in_confirm_action_names(self) -> None:
        """``CONFIRM_ACTION_NAMES`` 按生效档派生；guarded 永远不等于 safe，因此必在其中。"""
        assert DELETE.name in CONFIRM_ACTION_NAMES

    def test_direct_in_real_exposure(self) -> None:
        """真实 ``build_tool_exposure()``（不是 ``DIRECT_TOOLS`` 的原样回显）里是 direct。

        ``DIRECT_PATTERNS`` 里的 ``delete_*`` **匹配不到** ``ui_material_prep_delete_pack``
        这个前缀，所以这条只能靠显式并入 ``CONFIRM_ACTION_NAMES`` 成立。
        """
        assert build_tool_exposure().get(DELETE.name) == "direct"

    def test_registered_with_destructive_hint(self) -> None:
        """注册出去的注解必须让审批层判成「至少 HIGH」，否则这条动作会直通执行。"""
        tool = _register_into_probe([DELETE])[DELETE.name]
        annotations = tool.annotations
        assert annotations is not None
        assert annotations.destructive_hint is True, "guarded 动作注册成非破坏性 = 审批闸门不弹卡"
        assert annotations.read_only_hint is not True


class TestMaterialPrepAbsentVerifier:
    """核实三态：还在 → False、不在了 → True、查询报错 → None（不抛异常）。"""

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_three_states(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source = await MessageSource.objects.acreate(
            display_name="guarded 删除核实来源",
            sync_since=timezone.now(),
        )
        pack = await InboxMessage.objects.acreate(
            source=source,
            message_id="guarded-delete-pack",
            received_at=timezone.now(),
        )
        # 先抄下主键：``adelete()`` 会把实例上的 ``pk`` 置空（Django 的既定行为），
        # 直接用 ``pack.pk`` 核实会变成「packId 不是整数」的假失败。
        pack_id = pack.pk

        # ① 仍然存在：页面报成功也不算数，且措词必须禁止模型说「已删除」
        present = await verify.run_verifier(DELETE, {"packId": pack_id})
        assert present is not None
        assert present["verified"] is False
        assert f"仍能查到材料包 {pack.pk}" in present["note"]
        assert "不得说已删除" in present["note"]
        assert present["observed"] == {"packId": pack_id, "exists": True}

        # ② 真的删掉了：只有「查不到」才是核实通过
        await pack.adelete()
        gone = await verify.run_verifier(DELETE, {"packId": pack_id})
        assert gone is not None
        assert gone["verified"] is True
        assert f"材料包 {pack_id} 已不存在" in gone["note"]
        assert gone["observed"] == {"packId": pack_id, "exists": False}

        # ③ 查询本身报错：无法核实（None），绝不许冒泡成「动作失败」
        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise DatabaseError("连接断了")

        monkeypatch.setattr(InboxMessage.objects, "filter", _boom)
        broken = await verify.run_verifier(DELETE, {"packId": pack_id})
        assert broken is not None
        assert broken["verified"] is None, "核实过程报错 = 无法核实，不是「没删掉」"
        assert "无法核实" in broken["note"]

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_dirty_pack_id_is_unverifiable_not_false(self) -> None:
        """脏参数（灰度期旧前端 / JSON 往返）回 ``None``：不能把 ``filter`` 的异常扔给上游。"""
        dirty = await verify.run_verifier(DELETE, {"packId": "812"})
        assert dirty is not None
        assert dirty["verified"] is None
        assert "不是整数" in dirty["note"]
