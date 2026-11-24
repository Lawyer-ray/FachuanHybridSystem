"""举证期限（evidence_deadline）抽取回归测试 —— 行为契约冻结版。

这组用例锁三件事：

1. **举证/答辩期限只跟我方防守方**：「举证期限」是当事人向法院提交证据的义务，
   我方是原告时那是**对方**的义务；拿不到诉讼地位时不静默丢弃，但要标
   ``party_role_unknown`` 且不默认勾选（宁可让律师看一眼，也不替他做决定）。
2. **「法定下限」与「多档程序」都不算日期**：「不得少于十五日」是法定最低标准，
   不是法院指定的本案期限；「普通程序十五日／简易程序五日／小额三日」得由法官
   按实际程序选一档，替法院选程序就会算出一个看似精确、实则可能错的假期限。
   两种情况一律丢弃，并在 ``suppressed_out`` 留痕。
3. **纯日期兜底有「期限词」门槛**：只有原文写了「举证期限至…止」这类期限表述，
   才允许把明文日期当作届满日；叙事日期（「本院于X日公开开庭审理本案」）不得被
   兜底抓成期限。

另附两条护栏：既有上诉期抽取不得被新规则破坏；「举证期限为N日，自收到本通知书
之日起计算」这类**期限在前、起算句在后**的写法必须按送达日（``received_at``）推算，
而不是按落款日。

全部用例 ``analysis=None``（模拟 LLM 不可用/未报日期），只验证确定性规则层；
送达日固定 2026-11-24（与真实样本同一批送达）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from apps.document_recognition.services.data_classes import DocumentType
from apps.document_recognition.services.date_candidate_service import DateCandidateDraft, build_date_candidates

#: 法院短信 received_at = 本份文书送达日（与真实样本 id=29 同一时刻）
RECEIVED_AT = datetime(2026, 11, 24, 11, 13)

#: 我方是被告：防守方，举证/答辩期限是我方义务
DEFENDANT = ["defendant"]
#: 我方是原告：进攻方，举证期限是对方义务
PLAINTIFF = ["plaintiff"]

#: 期限在前、起算句在后（真实《举证通知书》的写法，落款为中文数字）
_PERIOD_THEN_ANCHOR = "举证期限为十五日，自收到本通知书之日起计算。二〇二六年十一月二十四日"
#: 同上但去掉落款：只能靠 received_at 起算
_PERIOD_THEN_ANCHOR_NO_SIGNATURE = "举证期限为十五日，自收到本通知书之日起计算。"
#: 真实样本：同一句里给了三档程序，选哪档取决于法院
_MULTI_TIER_TEXT = (
    "举证期限自当事人收到起诉状副本及举证通知书之日起计算，适用普通程序审理的案件，举证期限为十五日；"
    "适用简易程序审理的案件，举证期限为五日；适用小额诉讼程序审理的案件，举证期限为三日。"
)

CaseCheck = Callable[[str, list[DateCandidateDraft], list[dict[str, Any]]], None]


def _build(text: str, roles: list[str] | None) -> tuple[list[DateCandidateDraft], list[dict[str, Any]]]:
    """跑一次规则层，同时拿回候选与被闸门丢弃的留痕。"""
    suppressed: list[dict[str, Any]] = []
    drafts = build_date_candidates(
        text,
        None,
        DocumentType.OTHER,
        received_at=RECEIVED_AT,
        our_party_roles=roles,
        suppressed_out=suppressed,
    )
    return drafts, suppressed


def _pairs(drafts: list[DateCandidateDraft]) -> list[tuple[str, str]]:
    return [(draft.due_at.date().isoformat(), draft.reminder_type) for draft in drafts]


def _only(case_id: str, drafts: list[DateCandidateDraft]) -> DateCandidateDraft:
    assert len(drafts) == 1, f"[{case_id}] 期望恰好 1 条候选，实际 {_pairs(drafts)}"
    return drafts[0]


def _assert_suppressed_reason(case_id: str, suppressed: list[dict[str, Any]], keyword: str) -> None:
    """被丢弃的候选必须能在留痕里查到原因（律师问「为什么不提醒」时答得出）。"""
    reasons = [str(item.get("reason", "")) for item in suppressed]
    assert any(keyword in reason for reason in reasons), (
        f"[{case_id}] suppressed_out 里应有含「{keyword}」的丢弃原因，实际 {reasons}"
    )


# ---------------------------------------------------------------------------
# 每例一个断言函数：只断言该 case 关心的细节，基础条数/(日期,类型)由 parametrize 统一断言
# ---------------------------------------------------------------------------


def _check_case_01(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """被告 + 期限在前起算句在后：按送达日 + 15 天推算，且默认勾选。"""
    draft = _only(case_id, drafts)
    assert draft.derivation == "rule_period", f"[{case_id}] 应为期限推算 rule_period，实际 {draft.derivation}"
    assert draft.default_checked is True, f"[{case_id}] 防守方的举证期限应默认勾选"
    assert "本份文书送达日 2026-11-24" in draft.anchor_note, (
        f"[{case_id}] 起算点应写明送达日，实际 anchor_note={draft.anchor_note!r}"
    )


def _check_case_02(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """我方是原告：举证期限是对方义务，丢弃并在留痕里点明「对方」。"""
    assert drafts == [], f"[{case_id}] 原告方不应生成举证期限候选，实际 {_pairs(drafts)}"
    _assert_suppressed_reason(case_id, suppressed, "对方")


def _check_case_03(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """诉讼地位未知：保留候选让人核对，但挂 flag 且不默认勾选。"""
    draft = _only(case_id, drafts)
    assert "party_role_unknown" in draft.review_flags, (
        f"[{case_id}] 未确认地位应标 party_role_unknown，实际 flags={draft.review_flags}"
    )
    assert draft.default_checked is False, f"[{case_id}] 未确认地位不得默认勾选"


def _check_case_04(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """普通/简易/小额三档并列：不得替法院选程序，整体丢弃。"""
    assert drafts == [], f"[{case_id}] 多档程序不应生成任何候选，实际 {_pairs(drafts)}"
    _assert_suppressed_reason(case_id, suppressed, "多档")


def _check_case_05(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """「不得少于十五日」是法定下限，不是本案指定期限，丢弃。"""
    assert drafts == [], f"[{case_id}] 法定下限不应生成候选，实际 {_pairs(drafts)}"
    _assert_suppressed_reason(case_id, suppressed, "法定")


def _check_case_06(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """只有「期限为十五日」没有起算句：算不出届满日，丢弃并说明缺起算点。"""
    assert drafts == [], f"[{case_id}] 无起算点不应生成候选，实际 {_pairs(drafts)}"
    _assert_suppressed_reason(case_id, suppressed, "起算点")


def _check_case_07(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """答辩期同属防守方义务，按送达日 + 10 天推算，类型归 submission_deadline。"""
    draft = _only(case_id, drafts)
    assert draft.reminder_type == "submission_deadline", (
        f"[{case_id}] 答辩期应归 submission_deadline，实际 {draft.reminder_type}"
    )


def _check_case_08(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """「举证期限至X日止」：纯日期兜底，原文写明的届满日直接采信。"""
    draft = _only(case_id, drafts)
    assert draft.derivation == "rule_absolute", f"[{case_id}] 纯日期兜底应为 rule_absolute，实际 {draft.derivation}"


def _check_case_09(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """开庭日期是叙事事实，没有期限词，纯日期兜底不得抓成期限。"""
    assert drafts == [], f"[{case_id}] 叙事日期不应成为期限候选，实际 {_pairs(drafts)}"


def _check_case_10(case_id: str, drafts: list[DateCandidateDraft], suppressed: list[dict[str, Any]]) -> None:
    """既有上诉期抽取是护栏：新增的两道举证期限规则不得影响它。"""
    draft = _only(case_id, drafts)
    assert draft.reminder_type == "appeal_deadline", f"[{case_id}] 上诉期类型被破坏，实际 {draft.reminder_type}"


# ---------------------------------------------------------------------------
# 契约表：文本 / 我方地位 / 期望 (届满日, 类型) / 该例关心的细节
# ---------------------------------------------------------------------------

CASES = [
    pytest.param(
        "01",
        _PERIOD_THEN_ANCHOR,
        DEFENDANT,
        [("2026-12-09", "evidence_deadline")],
        _check_case_01,
        id="01_defendant_period_then_anchor",
    ),
    pytest.param(
        "02",
        _PERIOD_THEN_ANCHOR,
        PLAINTIFF,
        [],
        _check_case_02,
        id="02_plaintiff_role_suppressed",
    ),
    pytest.param(
        "03",
        _PERIOD_THEN_ANCHOR_NO_SIGNATURE,
        None,
        [("2026-12-09", "evidence_deadline")],
        _check_case_03,
        id="03_party_role_unknown_needs_review",
    ),
    pytest.param(
        "04",
        _MULTI_TIER_TEXT,
        DEFENDANT,
        [],
        _check_case_04,
        id="04_multi_tier_procedure_suppressed",
    ),
    pytest.param(
        "05",
        "举证期限不得少于十五日，自收到本通知书之日起计算。",
        DEFENDANT,
        [],
        _check_case_05,
        id="05_statutory_minimum_suppressed",
    ),
    pytest.param(
        "06",
        "举证期限为十五日。",
        DEFENDANT,
        [],
        _check_case_06,
        id="06_missing_anchor_suppressed",
    ),
    pytest.param(
        "07",
        "答辩期限为十日，自收到起诉状副本之日起计算。二〇二六年十一月二十四日",
        DEFENDANT,
        [("2026-12-04", "submission_deadline")],
        _check_case_07,
        id="07_answer_deadline_from_service_date",
    ),
    pytest.param(
        "08",
        "本案举证期限至2027年1月10日止。二〇二六年十一月二十四日",
        DEFENDANT,
        [("2027-01-10", "evidence_deadline")],
        _check_case_08,
        id="08_absolute_date_with_deadline_word",
    ),
    pytest.param(
        "09",
        "本院于2027年1月10日公开开庭审理本案。二〇二六年十一月二十四日",
        DEFENDANT,
        [],
        _check_case_09,
        id="09_narrative_date_not_a_deadline",
    ),
    pytest.param(
        "10",
        "如不服本判决，可以在判决书送达之日起十五日内上诉。二〇二六年十一月二十四日",
        DEFENDANT,
        [("2026-12-09", "appeal_deadline")],
        _check_case_10,
        id="10_existing_appeal_deadline_kept",
    ),
]


@pytest.mark.parametrize("case_id,text,roles,expect_pairs,check", CASES)
def test_evidence_deadline_contract(
    case_id: str,
    text: str,
    roles: list[str] | None,
    expect_pairs: list[tuple[str, str]],
    check: CaseCheck,
) -> None:
    """逐条对账「候选条数 + (届满日, 类型)」，再把该例特有的细节交给断言函数。"""
    drafts, suppressed = _build(text, roles)
    observed = _pairs(drafts)
    assert len(drafts) == len(expect_pairs), f"[{case_id}] 候选条数不符：期望 {len(expect_pairs)}，实际 {observed}"
    assert observed == expect_pairs, f"[{case_id}] (届满日, 类型) 不符：期望 {expect_pairs}，实际 {observed}"
    check(case_id, drafts, suppressed)
