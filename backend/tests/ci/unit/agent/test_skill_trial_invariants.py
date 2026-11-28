"""试跑 / 只读子 agent 的**工具面**不变量 —— 守「孤儿审批卡」这颗雷。

## 事故场景（本文件防的就是它）

试跑（``apps/agent/services/skills/trial.py``）为了让后端拿到 ``session_id``，用了
一个假会话 ``_TrialSession``，id 形如 ``skill-trial-<hex>``；这个 id 会被
``services/chat/env.py::session_env`` 写进 ``FACHUAN_SESSION_ID``，而 pi 的审批
extension 正是靠这个环境变量把审批回调**路由回「本会话」**。

所以只要 ``subtask.READONLY_PREFIXES`` 里混进一个 HIGH / CRITICAL 档的工具，试跑就会：
律师看到一张**不知道从哪来的**审批卡（背后那个会话根本不存在，前端也定位不到它）
→ 等满审批超时（``risk.DEFAULT_TIMEOUT``）后按 fail-closed 变成「被拒绝」→ 试跑侧
只收到一个空回复。同一个洞对只读子 agent（``subtask.readonly_tool_selection()``）
一模一样地成立。

今天不引爆纯属运气：白名单（``get_`` / ``list_`` / ``search_`` / ``read_`` /
``preview_``）恰好没撞上高危前缀。这份文件把那点运气换成门禁——谁把高危工具塞进
只读面，CI 立刻红。

## 四层（彼此独立，任一层红都算红）

1. **注册表对账**：注册表里所有被白名单命中的工具，逐个过
   ``classify_risk(全名, {}, annotations)``，结果只许 ``LOW`` / ``MEDIUM``；
2. **前缀探针（零依赖兜底）**：白名单的**前缀本身**不许命中 ``DANGER_PATTERNS``——
   第 1 层因为导入不出来而跳过时，这层仍然守着粗粒度的那一半；
3. **字形层**：白名单字符串里不许出现写动作片段；两个工具面里也不许出现 pi 的
   **裸**文件工具名（``read`` / ``bash`` / ...）——它们不带 ``mcp__`` 前缀，既不在
   审批清单内，也不受业务工具命名空间约束；
4. **试跑侧**：``TrialPlan.backend_kind`` 必须落在「能注入技能索引」的后端里，
   否则注入的正文根本没进模型，试跑验的是另一件事（假阴性 = 假成功）。

## 对应 ``docs/harness/pitfalls.md`` §0.2 的哪几个失败家族

- 家族 1「假成功」：只读面写着读前缀，里面却藏着会写 / 会外发的工具；
- 家族 3「静默退化」：白名单被随手加宽，没有任何报错，直到律师看见孤儿审批卡；
- 家族 5「门禁没通电」：所以第 1 层断言的是**活注册表**，不是文档里那份清单。

刻意**不**连库（全文没有 ``django_db``）：第 1 层读的是 ``mcp_server`` 进程内注册
表，第 4 层把查库的 ``_lawyer`` / ``_readable_skill`` 打掉，其余全是纯内存判定。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apps.agent.backends import SkillDelivery, registry
from apps.agent.backends.toolface import tool_prefix
from apps.agent.pi.rpc_client import TOOL_SELECTION
from apps.agent.services import subtask
from apps.agent.services.approval import (
    CRITICAL_PATTERNS,
    DANGER_PATTERNS,
    HARD_DENY_PATTERNS,
    RiskLevel,
    classify_risk,
)
from apps.agent.services.skills import trial
from apps.agent.services.skills.errors import SkillInvalid

#: 业务工具全名前缀（``mcp__fachuan__``），与 ``--tools`` 白名单同源。
_MCP_PREFIX = tool_prefix()

#: 只读面里出现 HIGH / CRITICAL 的后果——报错信息必须把这句话带上，否则下一个人
#: 只会看到「一个工具被判高危」，不知道它为什么和试跑有关。
_ORPHAN_CARD_WARNING = (
    "这会让试跑/只读子 agent 弹出孤儿审批卡（见 test_skill_trial_invariants 模块 docstring）"
)

#: 写动作片段：出现在只读白名单里就说明只读面被写工具污染了。
_WRITE_VERB_FRAGMENTS: tuple[str, ...] = (
    "save_",
    "delete_",
    "submit_",
    "update_",
    "create_",
    "apply_",
    "rewrite_",
    "execute_",
)

#: pi 自带、**不在审批清单内**的文件/命令工具。它们以 Django 进程权限读写文件、
#: 执行命令，一段藏在工具输出里的提示注入就能免审批执行，所以任何工具面都不许出现。
_BARE_FILE_TOOLS: frozenset[str] = frozenset(
    {"read", "bash", "edit", "write", "powershell", "grep", "find", "ls"}
)


def _selection_entries(selection: str) -> list[str]:
    """把 ``--tools`` 字符串拆成条目（``mcp__fachuan__get_*,tool_search`` → 两条）。"""
    return [entry.strip() for entry in selection.split(",") if entry.strip()]


def _selection_prefixes(selection: str) -> list[str]:
    """从 ``--tools`` 字符串反解白名单前缀（``mcp__fachuan__get_*`` → ``get_``）。

    刻意从 ``readonly_tool_selection()`` 的**返回值**反解，而不是直接读
    ``subtask.READONLY_PREFIXES``：真正喂给 pi 的是这个字符串，万一哪天两者漂移
    （比如有人把白名单硬编码进函数体），门禁必须跟着**真实工具面**走。

    不是「MCP 前缀 + 通配」形态的条目（例如将来可能加的 ``tool_search``）在这里
    被忽略——那类裸名由 :class:`TestToolFaceHasNoWriteOrBareFileTools` 单独管。
    """
    prefixes: list[str] = []
    for entry in _selection_entries(selection):
        if entry.startswith(_MCP_PREFIX) and entry.endswith("*"):
            prefixes.append(entry[len(_MCP_PREFIX) : -1])
    return prefixes


def _registered_tools() -> dict[str, Any]:
    """``mcp_server`` 的**活**注册表（短名 → 工具对象）。不起 MCP 服务、不连库。

    与 ``test_tool_registration.py`` 对账用的是同一份注册表：``_t`` 是唯一注册口
    （裸 ``mcp.tool()`` 被 ``test_tool_annotations`` 禁掉了），所以它就是全集。
    """
    try:
        from mcp_server.server import mcp
    except ImportError as exc:  # pragma: no cover - 裁剪过的环境里才有
        # 导入不出来就明说跳过，让第 2 层（前缀探针）顶上；**不能**静默当成通过。
        pytest.skip(f"mcp_server 不可导入，本层跳过（前缀探针层仍然生效）：{exc}")
    manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", None)
    if not isinstance(tools, dict) or not tools:
        # 空集会让本门禁**恒绿**——那比没有门禁更糟（家族 5 门禁没通电）。
        pytest.fail("读不到 mcp_server 工具注册表（结构变了？）：本门禁不允许静默退化成空集")
    return dict(tools)


def _declared_annotations(tool: Any) -> dict[str, Any] | None:
    """工具自报的 MCP 注解（键名与 ``approval.annotations`` 的表一致）。

    为什么不调 ``load_tool_annotations``：它走 ``mcp.list_tools()``（async + 线程里
    装事件循环），在门禁里既慢，又可能读到「插件工具还没注册完」的空表——空表会让
    ``classify_risk`` 退回纯名字判定，门禁就悄悄少守一层。直接读注册表里的同一个
    ``ToolAnnotations`` 对象，才是同一次快照、可重复的结果。
    """
    hints = getattr(tool, "annotations", None)
    if hints is None:
        return None
    return {
        "read_only_hint": getattr(hints, "read_only_hint", None),
        "destructive_hint": getattr(hints, "destructive_hint", None),
        "open_world_hint": getattr(hints, "open_world_hint", None),
    }


def _why(name: str, annotations: dict[str, Any] | None) -> str:
    """人话解释「这个工具为什么被判高危」——报错里要能直接看出该改哪里。"""
    reasons = [
        f"名字命中 {pattern!r}"
        for pattern in dict.fromkeys((*HARD_DENY_PATTERNS, *CRITICAL_PATTERNS, *DANGER_PATTERNS))
        if pattern in name
    ]
    if annotations:
        reasons.extend(
            f"注解 {key}=True" for key in ("destructive_hint", "open_world_hint") if annotations.get(key) is True
        )
    return "、".join(reasons) or "未命中已知高危模式（读 risk.classify_risk 的判定顺序）"


def _ensure_builtin_backends() -> None:
    """把内置后端放进注册表（幂等）。

    必须显式调：注册表是进程内全局状态，别的用例用过 ``registry.clear()`` 之后这里
    会读到空表（``backends/builtin.py`` 的 docstring 记录了实测事故：后续所有用例的
    ``stream_chat`` 全报「未知 agent backend: 'pi'」）。
    """
    from apps.agent.backends.builtin import ensure_registered

    ensure_registered()


def _injectable_kinds() -> set[str]:
    """能注入技能索引块的后端集合（= 试跑唯一允许的那一面）。

    刻意**不**复用 ``trial._can_inject``：门禁的判据必须独立于被测实现，否则
    ``_can_inject`` 自己写错时两边一起错，断言恒真。这里的口径是能力声明本身——
    ``skill_delivery`` 缺省即 ``tool_only``（见 ``SkillDelivery`` 的 docstring：
    「声明不实比没有更难查」）。
    """
    from apps.agent.backends import available_kinds, get

    injectable: set[str] = set()
    for kind in available_kinds():
        delivery = getattr(get(kind).capabilities, "skill_delivery", SkillDelivery.TOOL_ONLY)
        if delivery != SkillDelivery.TOOL_ONLY:
            injectable.add(kind)
    return injectable


def _fake_trial_skill() -> Any:
    """试跑要读的那一行（形状对齐 ``AgentSkill`` 的四个字段，不碰库）。"""
    return SimpleNamespace(pk=1048576, name="probe-skill", title="探针技能", scope="lawyer", body="探针正文", version=1)


class TestReadonlyToolFaceStaysLowRisk:
    """只读面（试跑 + 只读子 agent 共用）里的每一个工具都必须免审批。"""

    def test_registry_tools_matching_whitelist_are_low_or_medium(self) -> None:
        """防「只读白名单里混进 HIGH/CRITICAL」——那会让试跑弹孤儿审批卡。

        挑工具的口径必须与 pi 的 ``--tools`` 通配一致（``mcp__fachuan__get_*`` ⇒
        短名前缀匹配），否则门禁守的是一份**模型根本拿不到**的清单（家族 1）。
        注解取自注册表快照并显式传给 ``classify_risk``：注解层是插件自报风险的唯一
        来源（内置工具的 hint 由名字推导，这一层主要兜插件）。
        """
        tools = _registered_tools()
        selection = subtask.readonly_tool_selection()
        prefixes = tuple(_selection_prefixes(selection))
        assert prefixes, "反解不出白名单前缀——工具面格式变了，本门禁会恒绿（见 _selection_prefixes）"
        # 本层只对「前缀 + 通配」的条目对账。哪天白名单里出现指名的业务工具
        # （``mcp__fachuan__delete_case``，不带 ``*``），这里必须红：门禁看不见的
        # 条目等于没守（家族 5），而不是默默跳过。
        named = [
            entry
            for entry in _selection_entries(selection)
            if entry.startswith(_MCP_PREFIX) and not entry.endswith("*")
        ]
        assert not named, (
            f"只读白名单里出现指名条目 {named}：本门禁只对账「前缀*」形态，"
            "先把指名条目在这里补上对账再放行（否则它不会被任何一层审到）"
        )
        matched = sorted(name for name in tools if name.startswith(prefixes))
        assert matched, f"白名单 {prefixes} 在 {len(tools)} 个注册工具里一个都没命中：门禁恒绿，先修门禁"
        # 注解层要是整批为空，第 1 层就只剩名字判定——先确认快照里真有注解。
        assert any(_declared_annotations(tools[name]) for name in matched), (
            "注册表里的工具全都没声明注解：注解层形同虚设，本门禁会少守一半"
        )

        offenders: list[str] = []
        for name in matched:
            annotations = _declared_annotations(tools[name])
            level = classify_risk(f"{_MCP_PREFIX}{name}", {}, annotations if annotations is not None else {})
            if level not in (RiskLevel.LOW, RiskLevel.MEDIUM):
                offenders.append(f"{name} → {level}（{_why(name, annotations)}）")
        assert not offenders, (
            f"只读白名单 {prefixes} 命中了必须人工审批的工具：\n  - "
            + "\n  - ".join(offenders)
            + f"\n{_ORPHAN_CARD_WARNING}"
        )

    def test_whitelist_prefixes_do_not_hit_danger_patterns(self) -> None:
        """零依赖兜底：白名单的**前缀本身**不许命中 ``DANGER_PATTERNS``。

        这层不碰 MCP 注册表（注解传 ``{}``，不会触发注解表加载）。即使第 1 层因为
        导入失败而跳过，``delete_`` / ``submit_`` / ``rewrite_`` 这类前缀混进白名单
        仍然会在这里被抓住。传 ``{}`` 只会把下限抬到 MEDIUM（见
        ``_classify_by_annotations``），不会掩盖 HIGH / CRITICAL，所以断言只针对名字表。
        """
        prefixes = _selection_prefixes(subtask.readonly_tool_selection())
        assert prefixes, "反解不出白名单前缀——工具面格式变了，本门禁会恒绿（见 _selection_prefixes）"

        offenders: list[str] = []
        for prefix in prefixes:
            probe = f"{prefix}probe"
            level = classify_risk(f"{_MCP_PREFIX}{probe}", {}, {})
            if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                offenders.append(f"{prefix}* → {level}（{_why(probe, None)}）")
        assert not offenders, (
            "只读白名单的前缀本身命中高危模式：\n  - "
            + "\n  - ".join(offenders)
            + f"\n{_ORPHAN_CARD_WARNING}"
        )


class TestToolFaceHasNoWriteOrBareFileTools:
    """字形层：白名单里不许有写动作，工具面里不许有 pi 的裸文件工具。"""

    def test_readonly_selection_has_no_write_verb_fragments(self) -> None:
        """防「只读面被写工具污染」。

        白名单是**结构性安全**（``subtask`` 模块 docstring 第 2 条），不是提示词劝阻：
        工具面里一旦有写工具，模型中了提示注入就真有可作用的对象，无需任何审批。
        """
        selection = subtask.readonly_tool_selection()
        hits = [fragment for fragment in _WRITE_VERB_FRAGMENTS if fragment in selection]
        assert not hits, (
            f"只读工具面里出现写动作片段 {hits}：{selection}\n"
            "白名单只该是读类前缀；写工具进只读面 = 试跑 / 子 agent 能静默改律师的文件与数据。"
        )

    def test_tool_faces_have_no_bare_builtin_file_tools(self) -> None:
        """防「pi 内置文件工具混回工具面」——它们免审批且以 Django 进程权限运行。

        只认**条目级**的裸名：``mcp__fachuan__read_*`` 这种带前缀的通配只会命中我们
        自己的业务工具（短名 ``read_*``），碰不到 pi 内置的 ``read``；所以在整串里搜
        子串「read」会误报（``read_`` 里就有），必须按条目比对。

        与 ``test_skill_backend_invariants.py::TestReadonlyToolSelection`` 在只读面上
        有意重叠（同一口径的另一个角度）：那边只管 ``readonly_tool_selection()``，这里
        连 pi 的**主工具面** ``TOOL_SELECTION`` 一起管——两边都是安全边界，删掉一处
        还有另一处顶着。
        """
        faces = {
            "pi 主工具面 TOOL_SELECTION": TOOL_SELECTION,
            "只读面 readonly_tool_selection()": subtask.readonly_tool_selection(),
        }
        offenders: dict[str, list[str]] = {}
        for label, selection in faces.items():
            bare = [
                entry
                for entry in _selection_entries(selection)
                if not entry.startswith(_MCP_PREFIX) and entry.strip("*") in _BARE_FILE_TOOLS
            ]
            if bare:
                offenders[label] = bare
        assert not offenders, (
            f"工具面里出现 pi 的裸文件工具名：{offenders}\n"
            "它们不在审批清单内、以 Django 进程权限读写文件与执行命令——"
            "一段藏在工具输出里的提示注入就能免审批跑 bash。"
        )


class TestTrialBackendCanInjectSkillIndex:
    """试跑侧：``TrialPlan.backend_kind`` 必须是能注入索引块的后端。"""

    def test_default_trial_backend_is_injectable(self) -> None:
        """防「试跑跑在一个注不进技能的后端上」。

        ``tool_only`` 的后端把技能只当 MCP 工具暴露，系统提示里没有索引块；试跑注入
        的工作区正文（``skill_block_override``）进不了模型——审批人看到的回答与待审
        技能无关，却会当成「验过了」（家族 1 假成功）。
        """
        _ensure_builtin_backends()
        injectable = _injectable_kinds()
        assert injectable, "没有任何后端声明可注入技能索引：试跑无处可跑"
        kind = trial._resolve_backend_kind("")
        assert kind == "pi", f"试跑默认后端变了：{kind}（见 trial._default_backend_kind 的 docstring）"
        assert kind in injectable, f"试跑默认后端 {kind} 不能注入技能索引；可注入的有 {sorted(injectable)}"

    def test_prepare_trial_backend_kind_is_injectable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """防「准备阶段另算一套 kind」——真正发给后端的那个值必须落在可注入集合里。

        只读事实（``_lawyer`` / ``_readable_skill``）用 mock 打掉，所以本用例不连库：
        要验的是「kind 从哪来」，不是权限。
        """
        _ensure_builtin_backends()
        monkeypatch.setattr(trial.flags, "writes_enabled", lambda: True)
        monkeypatch.setattr(trial, "_lawyer", lambda user_id: object())
        monkeypatch.setattr(trial, "_readable_skill", lambda user_id, key, lawyer: _fake_trial_skill())
        # ``auto`` 会查交付面（``resolve_for_user``）来定 inline/index；本用例只要验
        # 「kind 从哪来」，所以把那一层也打掉，保持零 DB 依赖。
        monkeypatch.setattr(trial, "_deliverable_entry", lambda user_id, skill: None)

        plan = trial.prepare_trial(user_id=1, key="skill:1048576")
        assert plan.backend_kind in _injectable_kinds(), (
            f"TrialPlan.backend_kind={plan.backend_kind!r} 不能注入技能索引；"
            f"可注入的有 {sorted(_injectable_kinds())}"
        )

    def test_tool_only_backend_cannot_be_trialed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """防「可注入集合恒等于全部后端」——上一条断言若对任何后端都成立就是恒真。

        用 ``monkeypatch.setitem`` 而不是 ``registry.register()`` + ``registry.clear()``：
        ``clear()`` 是破坏性的（会连带清掉 ``pi``，见 ``_ensure_builtin_backends``），
        这里只想临时插一条，让 monkeypatch 在用例结束时自动摘掉。
        """
        _ensure_builtin_backends()
        kind = "trial-invariant-tool-only"
        backend = SimpleNamespace(kind=kind, capabilities=SimpleNamespace(skill_delivery=SkillDelivery.TOOL_ONLY))
        monkeypatch.setitem(registry._BACKENDS, kind, backend)  # type: ignore[arg-type]

        assert kind not in _injectable_kinds(), "tool_only 的后端被当成了可注入——可注入集合的判据坏了"
        with pytest.raises(SkillInvalid):
            trial._resolve_backend_kind(kind)
