"""立案前材料够不够（readiness）单测：模型只填要件，结论由确定性闸门给。

所有模型交互都用 fake `llm_caller` 注入：这里不联网、不碰数据库，也不 import
spec_service / facts_builder / draft_by_type——这一层只依赖要件档案与结构化输出工具。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import pytest

from apps.documents.services.draft.element_profiles import ELEMENT_PROFILES, QUESTION_BANK, ElementProfile, pick_profile
from apps.documents.services.draft.readiness import MATERIAL_SUMMARY_LIMIT, ReadinessResult, assess

LLMCaller = Callable[[list[dict[str, str]]], str]

#: 报告 4.2 要求 lease_arrears 必须含的 12 条要件（按中文 label 对齐）
REQUIRED_LEASE_LABELS = frozenset(
    {
        "合同成立生效",
        "我方权利来源",
        "付款义务与到期日",
        "未付事实",
        "金额计算",
        "催告与违约",
        "约定解除权",
        "解除通知或行使",
        "履约保证金（没收或抵扣）",
        "返还土地与地上物",
        "维权费用",
        "管辖与主体",
    }
)


def _json_caller(payload: dict[str, Any]) -> LLMCaller:
    def caller(messages: list[dict[str, str]]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    return caller


def _text_caller(text: str) -> LLMCaller:
    def caller(messages: list[dict[str, str]]) -> str:
        return text

    return caller


def _items(profile: ElementProfile, statuses: dict[str, str] | None = None) -> list[dict[str, str]]:
    """把档案里的每条要件都填成模型输出；statuses 只覆盖需要改的 key。"""
    overrides = statuses or {}
    return [
        {
            "requirement_key": requirement.key,
            "fact": "材料里有对应内容",
            "source": "合同 三、2",
            "status": overrides.get(requirement.key, "met"),
        }
        for requirement in profile.requirements
    ]


def _rows(result: ReadinessResult) -> dict[str, dict[str, Any]]:
    return {str(row["requirement_key"]): row for row in result.matrix}


class TestElementProfiles:
    def test_lease_profile_carries_all_required_requirements(self) -> None:
        profile = pick_profile("土地承包金欠付")
        assert profile.key == "lease_arrears"
        assert len(profile.requirements) >= 12
        assert {requirement.label for requirement in profile.requirements} >= REQUIRED_LEASE_LABELS
        for requirement in profile.requirements:
            assert requirement.key
            assert requirement.why
            assert requirement.evidence_forms

    def test_pick_profile_uses_lease_triggers(self) -> None:
        for cause in ("土地租赁合同纠纷", "承包金欠付", "租金纠纷", "土地承包经营纠纷"):
            assert pick_profile(cause).key == "lease_arrears"

    def test_pick_profile_falls_back_to_contract_payment(self) -> None:
        for cause in ("", "股权转让纠纷", "合同纠纷", "买卖合同纠纷"):
            assert pick_profile(cause).key == "contract_payment"
        assert len(ELEMENT_PROFILES["contract_payment"].requirements) >= 9

    def test_question_bank_covers_land_lease_checks(self) -> None:
        questions = QUESTION_BANK["lease_arrears"]
        assert len(questions) >= 6
        text = " ".join(question.question for question in questions)
        for topic in ("已支付", "付款节点", "交付", "送达地址", "保证金", "水费"):
            assert topic in text


class TestReadinessGates:
    def test_unknown_requirement_key_is_dropped_with_warning(self) -> None:
        profile = pick_profile("租赁合同纠纷")
        payload = {
            "items": [
                {"requirement_key": "invented_key", "fact": "编的", "source": "推断", "status": "met"},
            ]
        }
        result = assess(cause_of_action="租赁合同纠纷", llm_caller=_json_caller(payload))

        assert result.profile_key == "lease_arrears"
        assert {str(row["requirement_key"]) for row in result.matrix} == {
            requirement.key for requirement in profile.requirements
        }
        assert "invented_key" not in _rows(result)
        assert any("invented_key" in warning for warning in result.warnings)

    def test_omitted_requirement_is_filled_as_missing(self) -> None:
        profile = pick_profile("租赁合同纠纷")
        first = profile.requirements[0]
        payload = {
            "items": [
                {"requirement_key": first.key, "fact": "合同已签署", "source": "合同 签字页", "status": "met"},
            ]
        }
        result = assess(cause_of_action="租赁合同纠纷", llm_caller=_json_caller(payload))
        rows = _rows(result)

        assert len(rows) == len(profile.requirements)
        assert rows[first.key]["status"] == "met"
        assert all(rows[requirement.key]["status"] == "missing" for requirement in profile.requirements[1:])
        assert any("漏答" in warning for warning in result.warnings)

    def test_blocking_gap_yields_blocked(self) -> None:
        profile = pick_profile("租赁合同纠纷")
        payload = {
            "items": _items(profile),
            "missing_materials": [
                {
                    "item": "被告身份证复印件或户籍信息",
                    "why": "立案需明确被告并送达",
                    "from_whom": "委托人/律师调查",
                    "form": "复印件/公安查询单",
                    "severity": "blocking",
                }
            ],
        }
        result = assess(cause_of_action="租赁合同纠纷", llm_caller=_json_caller(payload))

        assert result.verdict == "blocked"
        assert result.blocking == ["被告身份证复印件或户籍信息"]

    def test_three_missing_without_blocking_yields_draftable_with_gaps(self) -> None:
        profile = pick_profile("租赁合同纠纷")
        statuses = {requirement.key: "missing" for requirement in profile.requirements[:3]}
        payload = {"items": _items(profile, statuses=statuses)}
        result = assess(cause_of_action="租赁合同纠纷", llm_caller=_json_caller(payload))

        assert result.verdict == "draftable_with_gaps"
        assert result.blocking == []

    def test_fewer_than_three_missing_without_blocking_yields_ready(self) -> None:
        profile = pick_profile("租赁合同纠纷")
        statuses = {requirement.key: "missing" for requirement in profile.requirements[:2]}
        statuses[profile.requirements[2].key] = "partial"
        payload = {"items": _items(profile, statuses=statuses)}
        result = assess(cause_of_action="租赁合同纠纷", llm_caller=_json_caller(payload))

        assert result.verdict == "ready"
        assert json.dumps(asdict(result), ensure_ascii=False)

    def test_llm_exception_yields_unknown_without_raising(self) -> None:
        def caller(messages: list[dict[str, str]]) -> str:
            raise RuntimeError("网关 502")

        result = assess(cause_of_action="租赁合同纠纷", llm_caller=caller)

        assert result.verdict == "unknown"
        assert all(row["status"] == "missing" for row in result.matrix)
        assert len(result.matrix) == len(ELEMENT_PROFILES["lease_arrears"].requirements)
        assert any("RuntimeError" in warning for warning in result.warnings)

    def test_invalid_json_yields_unknown_without_raising(self) -> None:
        result = assess(cause_of_action="租赁合同纠纷", llm_caller=_text_caller("{不是 JSON"))

        assert result.verdict == "unknown"
        assert all(row["status"] == "missing" for row in result.matrix)
        assert any("无法解析" in warning for warning in result.warnings)

    def test_missing_llm_caller_yields_unknown_without_raising(self) -> None:
        result = assess(cause_of_action="租赁合同纠纷")

        assert result.verdict == "unknown"
        assert result.profile_key == "lease_arrears"
        assert any("llm_caller" in warning for warning in result.warnings)

    def test_empty_input_does_not_crash(self) -> None:
        result = assess()

        assert result.verdict == "unknown"
        assert result.profile_key == "contract_payment"
        assert len(result.matrix) == len(ELEMENT_PROFILES["contract_payment"].requirements)
        assert all(row["status"] == "missing" for row in result.matrix)

    def test_empty_llm_payload_still_covers_all_requirements(self) -> None:
        result = assess(facts={}, material_summary="", cause_of_action="", llm_caller=_json_caller({}))

        assert result.verdict == "draftable_with_gaps"
        assert len(result.matrix) == len(ELEMENT_PROFILES["contract_payment"].requirements)
        assert all(row["status"] == "missing" for row in result.matrix)

    def test_system_prompt_forbids_inventing_material_facts(self) -> None:
        captured: dict[str, list[dict[str, str]]] = {}

        def caller(messages: list[dict[str, str]]) -> str:
            captured["messages"] = messages
            return json.dumps({"items": []}, ensure_ascii=False)

        assess(cause_of_action="租赁合同纠纷", llm_caller=caller)

        system = captured["messages"][0]["content"]
        assert "不得" in system
        for forbidden in ("主体名称", "金额", "日期"):
            assert forbidden in system

    def test_material_summary_is_truncated_and_declared_as_excerpt(self) -> None:
        captured: dict[str, str] = {}

        def caller(messages: list[dict[str, str]]) -> str:
            captured["user"] = messages[1]["content"]
            return json.dumps({"items": []}, ensure_ascii=False)

        result = assess(material_summary="合" * (MATERIAL_SUMMARY_LIMIT + 500), llm_caller=caller)

        assert "合" * MATERIAL_SUMMARY_LIMIT in captured["user"]
        assert "合" * (MATERIAL_SUMMARY_LIMIT + 1) not in captured["user"]
        assert "材料摘录（材料可能不完整）" in captured["user"]
        assert any(str(MATERIAL_SUMMARY_LIMIT) in warning for warning in result.warnings)


@dataclass(frozen=True)
class ReportCase:
    """报告 §二/§三 的真机案卷要点：律师函 + 14 页合同 OCR 前 2000 字（当事人名已脱敏）。"""

    facts: dict[str, str]
    material_summary: str
    cause_of_action: str
    payload: dict[str, Any]


@pytest.fixture
def report_case() -> ReportCase:
    return ReportCase(
        facts={
            "原告": "某农业公司",
            "被告": "张某",
            "案由": "土地租赁合同纠纷",
            "涉案金额": "404221.00",
        },
        material_summary=(
            "律师函（2026-11-16）：催告张某支付 2026 年 7-12 月管理维护费等四项，合计 404,221.00 元；"
            "称已多次催告仍未支付。"
            "《土地分包合同书》（14 页扫描件，OCR 仅核到前 2000 字）："
            "首个承包年度承包金 384,277 元应于 2026-05-08 前缴交；"
            "履约保证金变更后为 1,061,814.25 元；约定每日 3‰ 违约金。"
        ),
        cause_of_action="土地租赁合同纠纷",
        payload={
            "items": [
                {
                    "requirement_key": "contract_formation",
                    "fact": "《土地分包合同书》已由双方签字盖章",
                    "source": "合同 签字页",
                    "status": "met",
                },
                {
                    "requirement_key": "our_entitlement",
                    "fact": "原告为合同发包方",
                    "source": "合同 当事人页",
                    "status": "met",
                },
                {
                    "requirement_key": "payment_obligation_due_date",
                    "fact": "首个承包年度承包金 384,277 元应于 2026-05-08 前缴交",
                    "source": "合同 三、2",
                    "status": "met",
                },
                {
                    "requirement_key": "unpaid_fact",
                    "fact": "律师函称 2026 年 7-12 月管理维护费等四项未付；无对账单或银行流水",
                    "source": "律师函",
                    "status": "partial",
                },
                {
                    "requirement_key": "amount_calculation",
                    "fact": "合计 404,221.00 元只见于律师函，四项明细未与合同条款核对",
                    "source": "律师函",
                    "status": "partial",
                },
                {
                    "requirement_key": "contractual_termination_right",
                    "fact": "合同第九条解除条款在 OCR 摘录之外，未能核对",
                    "source": "（未核到）",
                    "status": "missing",
                },
                {
                    "requirement_key": "defendant_id_photo",
                    "fact": "张某的身份证号与户籍地址",
                    "source": "推断",
                    "status": "met",
                },
            ],
            "missing_materials": [
                {
                    "item": "被告身份证复印件或户籍信息",
                    "why": "立案需明确被告并送达",
                    "from_whom": "委托人/律师调查",
                    "form": "复印件/公安查询单",
                    "severity": "blocking",
                },
                {
                    "item": "欠款对账与银行流水",
                    "why": "未付事实需要客观凭证，律师函只是单方主张",
                    "from_whom": "委托人财务",
                    "form": "对账单/流水",
                    "severity": "blocking",
                },
                {
                    "item": "完整合同（签字盖章页与第九条全文）",
                    "why": "解除权与管辖条款在 OCR 摘录之外",
                    "from_whom": "委托人",
                    "form": "合同原件扫描件",
                    "severity": "amount",
                },
            ],
            "questions": [
                {
                    "to": "委托人经办人",
                    "question": "2026 年 6 月的管理维护费是否已缴？",
                    "why": "律师函只列 7-12 月",
                }
            ],
        },
    )


class TestRealCaseReportFixture:
    def test_unpaid_fact_partial_and_defendant_identity_blocking(self, report_case: ReportCase) -> None:
        result = assess(
            facts=report_case.facts,
            material_summary=report_case.material_summary,
            cause_of_action=report_case.cause_of_action,
            llm_caller=_json_caller(report_case.payload),
        )
        rows = _rows(result)

        assert result.profile_key == "lease_arrears"
        assert result.verdict == "blocked"
        assert len(result.matrix) == len(ELEMENT_PROFILES["lease_arrears"].requirements)

        # 未付事实：律师函只是单方主张，必须有流水/对账才够 → partial
        assert rows["unpaid_fact"]["status"] == "partial"
        # 被告身份材料：blocking 缺口，且模型编的 defendant_id_photo 必须被丢弃
        identity = [item for item in result.missing_materials if "被告身份" in item["item"]]
        assert identity and identity[0]["severity"] == "blocking"
        assert "被告身份证复印件或户籍信息" in result.blocking
        assert "defendant_id_photo" not in rows
        assert any("defendant_id_photo" in warning for warning in result.warnings)
        # OCR 摘录没覆盖到的第九条 / 管辖与主体：矩阵必须显式标 missing，不能静默消失
        assert rows["contractual_termination_right"]["status"] == "missing"
        assert rows["jurisdiction_and_parties"]["status"] == "missing"
        assert result.questions[0]["question"].startswith("2026 年 6 月")
        assert json.dumps(asdict(result), ensure_ascii=False)
