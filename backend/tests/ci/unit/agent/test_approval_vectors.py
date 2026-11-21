"""跨语言审批分级向量（golden vectors）的 Python 半边。

## 为什么需要这个文件

``approval-gate.ts`` 里的分级规则是服务端 ``risk.py`` 的镜像，但两侧**各自在
自己的语言里跑**：TS 侧其实从未被真正执行过——此前的一致性检查只是用正则从
源码里抠出数组字面量比文本（``test_agent_risk_tiers.py`` 的 ``_ts_list``）。
「表相同」掩盖了「判定不同」：注解缺失、短名归一这两条语义已经各自漂过
（2026-11 修正，见 ``approval-rules.ts`` 的注释与下面两条专项断言）。

本文件与 ``scripts/check-approval-parity.mjs`` 共用同一份向量
``tests/ci/fixtures/approval_vectors.json``：

- 这里断言 **Python（权威源）** 的判定与向量逐条一致；
- 那边用 ``node --experimental-strip-types`` 直接加载 ``approval-rules.ts``
  执行同一批向量。

任一侧改了规则却没同步向量，或两侧判定不一致，CI 都会红。改规则时的正确
姿势是：**先改 ``risk.py``（权威）→ 补/改向量 → 让 TS 侧与 parity 脚本变绿**。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from apps.agent.services.approval import HARD_DENY_PATTERNS, RiskLevel, classify_risk, is_high_risk
from apps.agent.services.approval import risk as risk_module

VECTORS_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "approval_vectors.json"
PI_DIR = Path(__file__).resolve().parents[4] / "apps" / "agent" / "pi"
RULES_TS = PI_DIR / "approval-rules.ts"
GATE_TS = PI_DIR / "approval-gate.ts"

#: 五张规则表的名字（与 `approval-rules.ts` 的导出同名；`HIGH_RISK_PATTERNS`
#: 就是 Python 侧的 `DANGER_PATTERNS`，名字差异是历史）。
TABLE_NAMES: tuple[str, ...] = (
    "HIGH_RISK_PATTERNS",
    "CRITICAL_PATTERNS",
    "HARD_DENY_PATTERNS",
    "SENSITIVE_ARG_MARKERS",
    "WRITE_PREFIXES",
)

VECTORS: list[dict[str, Any]] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

#: 必须被向量覆盖的判别样本：每一条都曾是两侧分叉或漏判的来源。
REQUIRED_NAMES: tuple[str, ...] = (
    "mcp__fachuan__clear_all_x",  # 批量清空 → 紧急 + 硬拒绝
    "mcp__fachuan__undelete_x",  # 子串 delete（不是前缀）
    "mcp__fachuan__file_lawsuit",  # file_ 递交
    "mcp__fachuan__batch_create_cases",  # batch_ 批量写
    "mcp__fachuan__parse_document",  # 精确圈定的写前缀
    "mcp__fachuan__remember",  # 记忆写
    "mcp__fachuan__recall_memory",  # 记忆读
    "mcp__fachuan__rewrite_folder_file",  # 2026-11 升级成高危
    "mcp__skill__delete_x",  # 非 fachuan 命名空间
    "mcp__fachuan__a__b",  # 多段命名空间（短名归一）
    "mcp__fachuan__ns__update_case",  # 短名归一的判别样本：Python 不会看 update_
)


def _is_hard_denied(tool_name: str) -> bool:
    """与 ``approval-rules.ts`` 的 ``isHardDenied`` 同义（命中任一模式即硬拒）。"""
    return any(pattern in tool_name for pattern in HARD_DENY_PATTERNS)


def _vector_id(vector: dict[str, Any], index: int) -> str:
    return f"{index:02d}-{vector['name']}-{vector['expected_level']}"


def _ts_table(source: str, name: str) -> list[str] | None:
    """从 TS 源码里抠出一张 `readonly string[]` 表（抠不到返回 ``None``）。"""
    match = re.search(rf"{name}: readonly string\[\] = \[(.*?)\]", source, re.S)
    if match is None:
        return None
    return re.findall(r'"([^"]+)"', match.group(1))


@pytest.mark.parametrize("vector", VECTORS, ids=[_vector_id(v, i) for i, v in enumerate(VECTORS)])
def test_vector_matches_authority(vector: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    """向量期望值必须与权威实现逐条一致（分级 + 是否兜底审批 + 硬拒绝）。

    注解表被钉成「该向量声明的那份」：真实注解表是进程级快照（从 ``mcp_server``
    注册表读一次），拿它来跑向量会让判定结果取决于有没有这个工具、以及它的
    注解长什么样——那就不是向量测试了。``annotations=null`` 的向量因此正好
    走「注解读不到 → 退回纯名字判定」这条路（服务端的既定语义）。
    """
    annotations = vector["annotations"]
    monkeypatch.setattr(risk_module, "load_tool_annotations", lambda _name: annotations)

    level = classify_risk(vector["name"], vector["args"], annotations)
    assert level.value == vector["expected_level"], vector.get("note", "")

    # is_high_risk 是「要不要拦」的单一入口，它不带 annotations 参数（走上面
    # 被钉住的注解表），必须给出与分级一致的结论。
    assert is_high_risk(vector["name"], vector["args"]) is (level in (RiskLevel.HIGH, RiskLevel.CRITICAL))

    # 硬拒绝层两侧同表：命中即 extension 直接 block（不进审批）。
    assert _is_hard_denied(vector["name"]) is vector["expected_hard_deny"], vector.get("note", "")


def test_vector_count_is_meaningful() -> None:
    """向量太少就守不住规则表（一次重构删掉一半也能全绿）。"""
    assert len(VECTORS) >= 40, f"向量只有 {len(VECTORS)} 条"


def test_required_cases_are_covered() -> None:
    """曾分叉/漏判的样本必须留在向量里，删掉就等于把坑重新埋回去。"""
    covered = {vector["name"] for vector in VECTORS}
    missing = [name for name in REQUIRED_NAMES if name not in covered]
    assert not missing, f"向量缺少必需样本: {missing}"


def test_expected_levels_are_valid() -> None:
    """期望值只能是四级之一——拼错会让 assert 永远失败得莫名其妙。"""
    valid = {level.value for level in RiskLevel}
    for vector in VECTORS:
        assert vector["expected_level"] in valid, vector["name"]


def test_rules_tables_are_not_duplicated_in_the_gate() -> None:
    """规则表只能有一份真值：`approval-gate.ts` 要么从 `approval-rules.ts` 导入，
    要么（过渡期）还带着一份**内容相同**的表（顺序无关，见下）。

    为什么需要这条：P2 把五张表与判定函数抽进了 `approval-rules.ts`，但切换
    `approval-gate.ts` 的那一刻，三个**既有**测试里扫 `approval-gate.ts` 的路径
    要同步改指（`test_agent_risk_tiers.py` 的 `_ts_list`、`test_toolface.py` 的
    前缀扫、`test_agent_runtime.py` 的模式扫）——那几处不在本次改动范围内。
    在切换完成之前，这条把「两边改了其中一边」变成红灯；切换完成后它自然
    退化成「gate 不再自带表」的断言。
    """
    rules_source = RULES_TS.read_text(encoding="utf-8")
    gate_source = GATE_TS.read_text(encoding="utf-8")
    gate_imports_rules = re.search(r'from "\./approval-rules(?:\.ts)?"', gate_source) is not None

    for name in TABLE_NAMES:
        rules_table = _ts_table(rules_source, name)
        assert rules_table is not None, f"approval-rules.ts 缺少 {name}"
        gate_table = _ts_table(gate_source, name)
        if gate_table is None:
            assert gate_imports_rules, f"approval-gate.ts 既没有 {name}，也没有从 approval-rules.ts 导入"
            continue
        # 比集合而不比顺序：子串匹配对顺序无关（`any`/`some` 命中即返回），
        # `test_agent_risk_tiers.py` 与 Python 对账时也是比集合。
        assert set(gate_table) == set(rules_table), (
            f"{name} 在 approval-gate.ts 与 approval-rules.ts 不一致（第二份真值已漂移）"
            f": only_gate={sorted(set(gate_table) - set(rules_table))}"
            f" only_rules={sorted(set(rules_table) - set(gate_table))}"
        )


def test_annotations_use_pi_side_key_names() -> None:
    """向量的注解键必须用 **pi 侧的 camelCase**（``readOnlyHint`` / ``destructiveHint``
    / ``openWorldHint``）。

    服务端从 ``mcp_server`` 注册表读到的注解是 snake_case（``load_tool_annotations``
    自己转换），两侧都认；但 extension 拿的是 pi ``getAllTools()`` 的 camelCase，
    而 TS 侧只认 camelCase。向量是两侧共用的输入，所以钉在**交集**上：
    加一条 snake_case 向量就会在 parity 脚本里挂——那正是需要先决定
    「TS 要不要也认 snake_case」的时候，不该悄悄放过去。
    """
    allowed = {"readOnlyHint", "destructiveHint", "openWorldHint"}
    for vector in VECTORS:
        annotations = vector["annotations"]
        if annotations is None:
            continue
        assert set(annotations) <= allowed, f"{vector['name']} 出现非 camelCase 注解键: {sorted(annotations)}"
