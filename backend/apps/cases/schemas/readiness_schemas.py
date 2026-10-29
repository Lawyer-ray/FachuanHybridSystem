"""案件就绪度 / 材料齐备度 / 利益冲突预检的 schema.

三个能力都是「律师在决定下一步动作前必须看到的判断依据」，
共同点是：**机器只给结论与出处，不代替人做决定**。
所以每个结果都带 `why`（依据）与 `source`（字段/表名），
让律师能核对「你凭什么这么说」，而不是只看到一个红绿灯。
"""

from __future__ import annotations

from typing import Literal

from ninja import Schema

# ───────────────────────── 材料齐备度 ─────────────────────────


class MaterialSlotOut(Schema):
    """一类材料的状态。

    status 语义（与原型 case-draft / reader 的取值一致）：
      ok      材料在，且是最新的
      stale   材料在，但截止日/版本旧了（不阻塞立案，建议先更新）
      miss    真缺件（阻塞立案）
      na      本案不适用（如无保证人则不需要担保合同）
    """

    key: str
    label: str
    status: Literal["ok", "stale", "miss", "na"]
    file_names: list[str] = []
    reason: str = ""


class MaterialStatusOut(Schema):
    """案件材料齐备度总览（对应原型「本案材料齐备」那一行）。

    为什么 single 值要单独给：律师最常问的是「这件能不能递」，
    一个布尔判断比 6 个槽位更好用；槽位则回答「还差哪一项」。
    """

    case_id: int
    slots: list[MaterialSlotOut]
    ok_count: int
    need_count: int
    missing_count: int
    stale_count: int
    ready: bool
    """ready = 没有 miss（stale 不阻塞立案，与原型口径一致）"""


# ───────────────────────── 案件就绪度（起诉/答辩条件）─────────────────────────


class ReadinessCheckOut(Schema):
    """一条条件的校验结果。

    与「状态徽章」的区别：徽章说「通过/不通过」，这里说**为什么**。
    `field` 给出判定所依据的模型字段，便于律师回溯数据源。
    """

    key: str
    label: str
    ok: bool
    detail: str
    field: str = ""
    """判定所依据的字段或表，如 Case.case_numbers / Case.target_amount"""


class CaseReadinessOut(Schema):
    """案件就绪度（起诉条件 / 答辩条件）。

    **按 current_stage 给不同的一组**，这是原型 case-draft 页的核心：
      一审未立案 → 起诉条件（主体/管辖/时效/材料/金额/利冲）
      二审        → 答辩条件（上诉理由/一审判决支撑/答辩期限）
    两组问的问题完全不同，混在一张表里律师不知道该看哪几行。
    """

    case_id: int
    stage: str
    mode: Literal["filing", "appeal", "other"]
    """"filing"=起诉条件 / "appeal"=答辩条件 / "other"=该阶段暂无专门校验"""

    checks: list[ReadinessCheckOut]
    passed: int
    total: int
    ready: bool
    """ready = 全部通过（缺件类为硬阻塞；提醒类不计入阻塞）"""


# ───────────────────────── 利益冲突预检 ─────────────────────────


class ConflictHitOut(Schema):
    """一条潜在冲突。

    level 三档与原型一致：
      red       同名 + 证件号相同 → 确定冲突，必须停
      yellow    同名但证件号不同 → 疑似，需人工复核
      neutral   无证件号可比对 → 提示，通常是历史数据不全
    """

    level: Literal["red", "yellow", "neutral"]
    party_name: str
    legal_status: str
    matched_client_id: int | None = None
    matched_client_name: str = ""
    matched_case_id: int | None = None
    matched_case_name: str = ""
    reason: str = ""
    id_matched: bool = False


class ConflictCheckOut(Schema):
    case_id: int
    checked_parties: int
    hits: list[ConflictHitOut]
    blocked: bool
    """blocked = 存在 red 级命中，后续动作应被阻断（由前端执行）"""
