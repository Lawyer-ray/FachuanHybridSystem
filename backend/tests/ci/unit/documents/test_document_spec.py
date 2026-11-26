"""文书起草规格（DocumentSpec）测试。

覆盖：
- 规格唯一键；查不到规格就是 None（绝不拿默认格式兜底）
- resolve_slot_values 四类取值路径（fixed / slot / llm / pending），
  且 context 的键必须全是骨架里真实存在的占位符
- 种子命令：幂等；缺骨架时整条命令失败（不许种一半）
"""

from __future__ import annotations

from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction

from apps.documents.admin.document_spec_admin import DocumentSpecForm
from apps.documents.models import DocumentSpec, DocumentTemplate, FolderSlot
from apps.documents.models.document_spec import SlotSource
from apps.documents.services.document_template.placeholder_extractor import extract_placeholders
from apps.documents.services.draft.spec_service import get_spec, list_specs, resolve_slot_values

COMPLAINT_TEMPLATE_PATH = "2-案件材料/1-起诉材料/1-起诉状和反诉答辩状/1-起诉状.docx"
DEFENSE_TEMPLATE_PATH = "2-案件材料/2-答辩材料/1-答辩状和反诉状/1-答辩状.docx"

#: 起诉状骨架里真实存在的占位符：解析出来的键必须落在这个集合里，否则渲染时会被静默忽略
COMPLAINT_PLACEHOLDERS = {"起诉状当事人信息", "诉讼请求", "事实与理由", "审理机构", "起诉状签名盖章信息"}


@pytest.fixture
def complaint_template(db: Any) -> DocumentTemplate:
    return DocumentTemplate.objects.create(
        name="起诉状",
        template_type="case",
        case_types=["all"],
        file_path=COMPLAINT_TEMPLATE_PATH,
    )


@pytest.fixture
def defense_template(db: Any) -> DocumentTemplate:
    return DocumentTemplate.objects.create(
        name="答辩状",
        template_type="case",
        case_types=["all"],
        file_path=DEFENSE_TEMPLATE_PATH,
    )


def make_spec(template: DocumentTemplate | None, **overrides: Any) -> DocumentSpec:
    payload: dict[str, Any] = {"doc_type": "unit_spec", "display_name": "单元测试文书", "skeleton_template": template}
    payload.update(overrides)
    return DocumentSpec.objects.create(**payload)


class TestSkeletonPlaceholders:
    def test_complaint_skeleton_placeholders_are_as_expected(self, complaint_template: DocumentTemplate) -> None:
        """骨架变了这条会红：解析器的认领规则完全建立在这组占位符名上。"""
        assert set(extract_placeholders(complaint_template.get_file_location())) == COMPLAINT_PLACEHOLDERS


class TestGetSpec:
    def test_missing_doc_type_returns_none(self, db: Any) -> None:
        assert get_spec("jurisdiction_objection") is None
        assert get_spec("") is None

    def test_inactive_spec_is_not_draftable(self, complaint_template: DocumentTemplate) -> None:
        make_spec(complaint_template, doc_type="paused", is_active=False)
        assert get_spec("paused") is None
        assert list_specs() == []
        assert [spec.doc_type for spec in list_specs(active_only=False)] == ["paused"]

    def test_doc_type_is_unique(self, complaint_template: DocumentTemplate) -> None:
        make_spec(complaint_template, doc_type="dup")
        with pytest.raises(IntegrityError), transaction.atomic():
            make_spec(complaint_template, doc_type="dup")


class TestResolveSlotValues:
    def test_context_keys_are_real_skeleton_placeholders(self, complaint_template: DocumentTemplate) -> None:
        spec = make_spec(complaint_template, claim_slot_key="诉讼请求", facts_slot_key="事实与理由")
        context, pending = resolve_slot_values(spec, facts={"诉讼请求": "1. 判令被告返还借款。"})
        assert set(context) <= COMPLAINT_PLACEHOLDERS
        assert set(pending) <= COMPLAINT_PLACEHOLDERS

    def test_fixed_source_uses_claim_text(self, complaint_template: DocumentTemplate) -> None:
        spec = make_spec(
            complaint_template,
            claim_source=SlotSource.FIXED,
            claim_text="请求依法驳回原告的全部诉讼请求。",
            claim_slot_key="诉讼请求",
        )
        context, _ = resolve_slot_values(spec)
        assert context["诉讼请求"] == "请求依法驳回原告的全部诉讼请求。"

    def test_slot_source_reads_same_name_fact(self, complaint_template: DocumentTemplate) -> None:
        spec = make_spec(
            complaint_template,
            claim_source=SlotSource.SLOT,
            claim_slot_key="诉讼请求",
            facts_source=SlotSource.SLOT,
            facts_slot_key="事实与理由",
        )
        context, pending = resolve_slot_values(
            spec, facts={"诉讼请求": "1. 判令被告返还借款。", "事实与理由": "被告到期未还。"}
        )
        assert context["诉讼请求"] == "1. 判令被告返还借款。"
        assert context["事实与理由"] == "被告到期未还。"
        assert "诉讼请求" not in pending
        assert "事实与理由" not in pending

    def test_llm_source_writes_section(self, complaint_template: DocumentTemplate) -> None:
        calls: list[list[dict[str, str]]] = []

        def fake_caller(messages: list[dict[str, str]]) -> str:
            calls.append(messages)
            return "判令被告于判决生效之日起十日内返还借款。"

        spec = make_spec(
            complaint_template,
            claim_source=SlotSource.LLM,
            claim_slot_key="诉讼请求",
            facts_source=SlotSource.SLOT,
            facts_slot_key="事实与理由",
            ai_brief="只写还款请求，不写利息",
        )
        context, _ = resolve_slot_values(spec, facts={"事实与理由": "被告到期未还。"}, llm_caller=fake_caller)
        assert context["诉讼请求"] == "判令被告于判决生效之日起十日内返还借款。"
        assert len(calls) == 1
        assert calls[0][0]["role"] == "system"
        assert "只写还款请求，不写利息" in calls[0][0]["content"]
        assert "被告到期未还。" in calls[0][1]["content"]

    def test_llm_failure_becomes_pending_instead_of_raising(self, complaint_template: DocumentTemplate) -> None:
        def exploding_caller(messages: list[dict[str, str]]) -> str:
            raise RuntimeError("模型超时")

        spec = make_spec(complaint_template, claim_source=SlotSource.LLM, claim_slot_key="诉讼请求")
        context, pending = resolve_slot_values(spec, llm_caller=exploding_caller)
        assert "诉讼请求" not in context
        assert "诉讼请求" in pending

    def test_nothing_to_fill_means_every_placeholder_is_pending(self, complaint_template: DocumentTemplate) -> None:
        spec = make_spec(complaint_template)
        context, pending = resolve_slot_values(spec)
        assert context == {}
        assert set(pending) == COMPLAINT_PLACEHOLDERS

    def test_extra_slot_is_pending_until_lawyer_provides_it(self, complaint_template: DocumentTemplate) -> None:
        spec = make_spec(
            complaint_template,
            extra_slots=[{"key": "原受理法院", "label": "原受理法院", "source": SlotSource.SLOT.value}],
        )
        _, pending = resolve_slot_values(spec)
        assert "原受理法院" in pending

        _, pending_with_fact = resolve_slot_values(spec, facts={"原受理法院": "北京市朝阳区人民法院"})
        assert "原受理法院" not in pending_with_fact

    def test_defense_claim_merges_into_single_body_placeholder(self, defense_template: DocumentTemplate) -> None:
        """答辩状骨架只有一个正文占位符：答辩请求不能因为「没位置」被丢掉。"""
        spec = make_spec(
            defense_template,
            doc_type="defense",
            claim_source=SlotSource.FIXED,
            claim_text="请求依法驳回原告的全部诉讼请求。",
            facts_source=SlotSource.SLOT,
            facts_slot_key="答辩理由",
        )
        context, _ = resolve_slot_values(spec, facts={"答辩理由": "原告主张与事实不符。"})
        assert context["答辩理由"] == "请求依法驳回原告的全部诉讼请求。\n原告主张与事实不符。"

    def test_seeded_shape_resolves_without_explicit_slot_keys(self, complaint_template: DocumentTemplate) -> None:
        """种子数据不写 claim_slot_key / facts_slot_key：靠骨架族的标准节名认领。"""
        replies = iter(["1. 判令被告返还借款。", "被告到期未还。"])
        spec = make_spec(complaint_template, doc_type="complaint")
        context, _ = resolve_slot_values(spec, llm_caller=lambda messages: next(replies))
        assert context == {"诉讼请求": "1. 判令被告返还借款。", "事实与理由": "被告到期未还。"}

    def test_no_skeleton_reports_declared_slots_only(self, db: Any) -> None:
        spec = make_spec(
            None,
            doc_type="no_skeleton",
            claim_slot_key="诉讼请求",
            extra_slots=[{"key": "原受理法院", "label": "原受理法院"}],
        )
        context, pending = resolve_slot_values(spec)
        assert context == {}
        assert pending == ["诉讼请求", "原受理法院"]


class TestDocumentSpecAdminForm:
    def test_extra_slots_accepts_json_array_and_rejects_other_shapes(self, db: Any) -> None:
        base = {
            "doc_type": "admin_form_probe",
            "display_name": "表单校验",
            "family": "litigation_v1",
            "claim_source": "llm",
            "facts_source": "llm",
        }

        accepted = DocumentSpecForm(
            data={**base, "extra_slots": '[{"key": "原受理法院", "label": "原受理法院", "source": "slot"}]'}
        )
        assert accepted.is_valid(), accepted.errors
        assert accepted.cleaned_data["extra_slots"] == [{"key": "原受理法院", "label": "原受理法院", "source": "slot"}]

        # 写成对象而不是数组：解析器按数组遍历，存下来就是错的，必须在保存前拦住
        not_a_list = DocumentSpecForm(data={**base, "extra_slots": '{"key": "原受理法院"}'})
        assert not not_a_list.is_valid()
        assert "extra_slots" in not_a_list.errors

        broken_json = DocumentSpecForm(data={**base, "extra_slots": "[oops"})
        assert not broken_json.is_valid()
        assert "extra_slots" in broken_json.errors


class TestSeedCommand:
    def test_seed_is_idempotent(self, complaint_template: DocumentTemplate, defense_template: DocumentTemplate) -> None:
        call_command("seed_document_specs", verbosity=0)
        first_run = {spec.doc_type: spec.pk for spec in DocumentSpec.objects.all()}
        assert len(first_run) == 3

        call_command("seed_document_specs", verbosity=0)
        assert {spec.doc_type: spec.pk for spec in DocumentSpec.objects.all()} == first_run
        assert FolderSlot.objects.filter(key="jurisdiction_objection").count() == 1

        objection = DocumentSpec.objects.get(doc_type="jurisdiction_objection")
        assert objection.display_name == "管辖权异议申请书"
        assert objection.title_override == "管辖权异议申请书"
        # 复用起诉状骨架：零新 docx
        assert objection.skeleton_template_id == complaint_template.pk
        assert objection.folder_slot == "jurisdiction_objection"
        assert objection.party_label == "异议人"
        assert objection.claim_heading == "异议请求："
        assert objection.extra_slots == [{"key": "原受理法院", "label": "原受理法院", "source": "slot"}]

        defense = DocumentSpec.objects.get(doc_type="defense")
        assert defense.skeleton_template_id == defense_template.pk
        assert defense.claim_source == "fixed"
        assert defense.claim_text == "请求依法驳回原告的全部诉讼请求。"

        slot = FolderSlot.objects.get(key="jurisdiction_objection")
        assert slot.name == "管辖权异议"
        assert slot.category == "filing"

    def test_missing_skeleton_seeds_nothing(self, complaint_template: DocumentTemplate) -> None:
        with pytest.raises(CommandError) as error:
            call_command("seed_document_specs", verbosity=0)
        assert DEFENSE_TEMPLATE_PATH in str(error.value)
        assert DocumentSpec.objects.count() == 0
        assert not FolderSlot.objects.filter(key="jurisdiction_objection").exists()
