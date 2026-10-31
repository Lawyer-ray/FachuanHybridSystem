"""案件就绪度服务单元测试.

覆盖三个能力的关键判定分支——**尤其是「不该报冲突时不能报」**：
  ① MaterialStatusService  缺件 / 不适用（无保证人）/ 齐备
  ② CaseReadinessService   起诉条件 vs 答辩条件按 current_stage 分流
  ③ ConflictCheckService   red / yellow / neutral 三档不能混

为什么重点测反例：
  这三块都是「机器给律师下判断」。误报（把正常说成冲突）比漏报更伤——
  律师会对告警脱敏，之后真的冲突也不看了。
"""

from __future__ import annotations

import pytest

from apps.cases.models.material import CaseMaterial
from apps.cases.models.party import CaseParty
from apps.cases.services.case_readiness_service import CaseReadinessService, ConflictCheckService, MaterialStatusService
from apps.testing.factories import CaseFactory, ClientFactory

pytestmark = pytest.mark.django_db


# ───────────────────────── 材料齐备度 ─────────────────────────


class TestMaterialStatus:
    def test_empty_case_all_missing(self):
        """空案件：除「担保合同」外全部 miss，ready=False。"""
        case = CaseFactory()
        result = MaterialStatusService().status_of(case.id)

        by_key = {s["key"]: s for s in result["slots"]}
        assert by_key["contract"]["status"] == "miss"
        assert by_key["iou"]["status"] == "miss"
        # 无保证人 → 担保合同不适用，不算缺件
        assert by_key["guarantee"]["status"] == "na"
        assert result["ready"] is False
        assert result["missing_count"] == 5  # 6 项里扣掉不适用那 1 项

    def test_material_matched_by_keyword(self):
        """材料类型名/文件名含关键词即归入对应槽位。

        ⚠️ CaseMaterial 没有 file_path 字段——文件名在 source_attachment 里，
        没有附件时退回用 type_name 匹配。这里用 type_name 验证归位逻辑。
        """
        case = CaseFactory()
        CaseMaterial.objects.create(
            case=case,
            category="party",
            type_name="借款合同",
        )
        result = MaterialStatusService().status_of(case.id)
        by_key = {s["key"]: s for s in result["slots"]}
        assert by_key["contract"]["status"] == "ok"
        # 没有附件时 file_names 退回 "材料#<id>"，不空即可
        assert by_key["contract"]["file_names"], "命中槽位必须给出可读标识"

    def test_guarantee_required_when_guarantor_exists(self):
        """有担保人当事人时，担保合同不再是 na 而是 miss。"""
        case = CaseFactory()
        CaseParty.objects.create(case=case, client=_client("担保人甲"), legal_status="guarantor")

        result = MaterialStatusService().status_of(case.id)
        by_key = {s["key"]: s for s in result["slots"]}
        assert by_key["guarantee"]["status"] == "miss"
        assert result["ready"] is False

    def test_missing_case_raises(self):
        with pytest.raises(ValueError, match="案件不存在"):
            MaterialStatusService().status_of(999999)


# ───────────────────────── 起诉 / 答辩条件分流 ─────────────────────────


class TestCaseReadiness:
    def test_first_trial_uses_filing_checks(self):
        """一审（含未填阶段）走起诉条件，不问答辩的事。"""
        case = CaseFactory(current_stage="first_trial")
        result = CaseReadinessService().readiness_of(case.id)

        assert result["mode"] == "filing"
        keys = {c["key"] for c in result["checks"]}
        assert "parties" in keys and "jurisdiction" in keys and "materials" in keys
        # 二审特有的校验不该出现在一审
        assert "previous" not in keys and "judgment" not in keys

    def test_second_trial_uses_appeal_checks(self):
        """二审走答辩条件：必须挂前序案件、要有判决书。"""
        first = CaseFactory(current_stage="first_trial")
        del first  # 回归点:二审未挂前序时必须判不通过，不靠前序案件
        appeal = CaseFactory(current_stage="second_trial", previous_case=None)
        result = CaseReadinessService().readiness_of(appeal.id)

        assert result["mode"] == "appeal"
        by_key = {c["key"]: c for c in result["checks"]}
        # 未挂前序 → 不通过，且 detail 要说明原因
        assert by_key["previous"]["ok"] is False
        assert "前序" in by_key["previous"]["detail"]
        assert result["ready"] is False
        # 起诉条件那套不该出现
        assert "jurisdiction" not in by_key

    def test_appeal_with_previous_case_passes_that_check(self):
        first = CaseFactory(current_stage="first_trial")
        appeal = CaseFactory(current_stage="second_trial", previous_case=first)
        result = CaseReadinessService().readiness_of(appeal.id)
        by_key = {c["key"]: c for c in result["checks"]}
        assert by_key["previous"]["ok"] is True

    def test_unknown_stage_returns_empty_not_fake_pass(self):
        """其他阶段（执行/仲裁）暂无校验——要明确返回空，不要假装 ready。"""
        case = CaseFactory(current_stage="enforcement")
        result = CaseReadinessService().readiness_of(case.id)
        assert result["mode"] == "other"
        assert result["checks"] == []
        assert result["total"] == 0

    def test_every_check_carries_field_and_detail(self):
        """每条校验都必须能回溯依据（field）并说清原因（detail）。"""
        case = CaseFactory(current_stage="first_trial")
        result = CaseReadinessService().readiness_of(case.id)
        for c in result["checks"]:
            assert c["field"], f"{c['key']} 缺 field"
            assert c["detail"], f"{c['key']} 缺 detail"


# ───────────────────────── 利益冲突三档 ─────────────────────────


class TestConflictCheck:
    def test_no_hit_when_single_case(self):
        """只有本案时不该报任何冲突。"""
        case = CaseFactory()
        CaseParty.objects.create(case=case, client=_client("张三", "440101199001011234"), legal_status="defendant")
        result = ConflictCheckService().check(case.id)
        assert result["hits"] == []
        assert result["blocked"] is False

    def test_red_when_same_name_and_id(self):
        """同名且证件号相同 → red，必须阻断。"""
        c1 = CaseFactory()
        c2 = CaseFactory()
        shared = _client("李四", "440101199001015678")
        CaseParty.objects.create(case=c1, client=shared, legal_status="defendant")
        CaseParty.objects.create(case=c2, client=shared, legal_status="plaintiff")

        result = ConflictCheckService().check(c1.id)
        assert len(result["hits"]) == 1
        assert result["hits"][0]["level"] == "red"
        assert result["hits"][0]["id_matched"] is True
        assert result["blocked"] is True

    def test_yellow_when_same_name_different_id(self):
        """同名但证件号不同 → yellow（疑似重名），不能阻断。"""
        c1 = CaseFactory()
        c2 = CaseFactory()
        CaseParty.objects.create(case=c1, client=_client("王五", "440101199001011111"), legal_status="defendant")
        CaseParty.objects.create(case=c2, client=_client("王五", "440101199001012222"), legal_status="plaintiff")

        result = ConflictCheckService().check(c1.id)
        assert len(result["hits"]) == 1
        assert result["hits"][0]["level"] == "yellow"
        assert result["hits"][0]["id_matched"] is False
        # 关键：疑似不等于冲突，不该阻断
        assert result["blocked"] is False

    def test_neutral_when_id_missing(self):
        """缺证件号 → neutral（提示补全资料），也不是冲突。"""
        c1 = CaseFactory()
        c2 = CaseFactory()
        CaseParty.objects.create(case=c1, client=_client("赵六", ""), legal_status="defendant")
        CaseParty.objects.create(case=c2, client=_client("赵六", ""), legal_status="plaintiff")

        result = ConflictCheckService().check(c1.id)
        assert len(result["hits"]) == 1
        assert result["hits"][0]["level"] == "neutral"
        assert result["blocked"] is False

    def test_no_parties_returns_clean(self):
        result = ConflictCheckService().check(CaseFactory().id)
        assert result["checked_parties"] == 0
        assert result["hits"] == []


class TestStageAndStatusEncodingCompat:
    """`current_stage` / `legal_status` 的中英文混存兼容。

    ═══ 这组测试守的是一个**已上线的真实缺陷** ═══
    生产库 `cases_case.current_stage` 是混存的：
        first_trial 48 件 / enforcement 18 件 / 一审 13 件 / second_trial 7 件 / 二审 1 件
    `cases_caseparty.legal_status` 同样：defendant 73 / plaintiff 45 / 被告 3 …
    早期实现只认英文枚举，后果是：
      · 那 13 件「一审」全落进 mode="other"，checks 为空、**ready 恒为 True**
        —— 律师看到「全部通过」，实际一条都没校验过。静默假通过比报错更危险。
      · 那 3 个「被告」不被算作被告 → 误判「主体不适格」。
    """

    def test_chinese_first_trial_uses_filing_checks(self):
        """存「一审」的一律走起诉条件，不能掉进 other。"""
        case = CaseFactory(current_stage="一审")
        result = CaseReadinessService().readiness_of(case.id)
        assert result["mode"] == "filing"
        assert result["total"] > 0, "空 checks + ready=True 就是静默假通过"

    def test_chinese_second_trial_uses_appeal_checks(self):
        """存「二审」的走答辩条件。"""
        first = CaseFactory(current_stage="一审")
        appeal = CaseFactory(current_stage="二审", previous_case=first)
        result = CaseReadinessService().readiness_of(appeal.id)
        assert result["mode"] == "appeal"
        assert any(c["key"] == "previous" for c in result["checks"])

    def test_chinese_legal_status_counts_as_plaintiff_and_defendant(self):
        """「原告/被告」的写法也要被认出来，否则误判主体不适格。"""
        case = CaseFactory(current_stage="first_trial")
        CaseParty.objects.create(case=case, client=_client("甲公司"), legal_status="原告")
        CaseParty.objects.create(case=case, client=_client("乙某"), legal_status="被告")

        result = CaseReadinessService().readiness_of(case.id)
        parties = next(c for c in result["checks"] if c["key"] == "parties")
        assert parties["ok"] is True, parties["detail"]

    def test_unknown_stage_is_explicit_not_silently_ready(self):
        """真正不认识的阶段：允许 mode=other，但必须没有 checks 且 total=0。"""
        case = CaseFactory(current_stage="执行")
        result = CaseReadinessService().readiness_of(case.id)
        assert result["mode"] == "other"
        assert result["checks"] == []
        assert result["total"] == 0


# ───────────────────────── helpers ─────────────────────────


def _client(name: str, id_number: str = ""):
    """建一个自然人客户。id_number 传空串表示「数据不全」那一档。"""
    return ClientFactory(name=name, id_number=id_number or None)
