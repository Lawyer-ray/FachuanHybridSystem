"""材料摘录的两条口径：归案时绑定的解析任务优先，文件名匹配只作存量兜底。

真机基线（docs/analysis/legal-doc-generation-2026-11-26/07 §D2）：
- DeepSeek OCR 后端只写 `text`，`ParsedDocument.markdown` 恒为 None；
- 开发库 84 条 completed 解析任务里 35 条 `markdown` 为空（backend_used=mineru）。
只读 `markdown` + 只按文件名匹配的旧写法，会让材料**静默缺席**起草提示词：
模型拿不到合同，成稿里也看不出少了一整份证据。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from apps.cases.models.log import CaseLogAttachment as CaseLogAttachmentStub
from apps.document_parsing.models import DocumentParsingTask
from apps.documents.services.draft import facts_builder


def _task(filename: str, *, markdown: str, text: str) -> DocumentParsingTask:
    return DocumentParsingTask.objects.create(
        file_name=filename,
        file_path=f"/tmp/{filename}",
        status=DocumentParsingTask.Status.COMPLETED,
        backend_used="deepseek",
        markdown=markdown,
        text=text,
    )


def _material(*, filename: str, task: DocumentParsingTask | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        source_attachment=SimpleNamespace(original_filename=filename, file=SimpleNamespace(name=filename)),
        parsing_task=task,
    )


def _case(*materials: SimpleNamespace) -> Any:
    """只提供 `materials.select_related(...)` 这一条被用到的协议。"""

    class _Materials(list):  # type: ignore[type-arg]
        def select_related(self, *_args: Any, **_kwargs: Any) -> Any:
            return self

    return SimpleNamespace(materials=_Materials(materials))


@pytest.mark.django_db
def test_linked_task_is_used_before_filename_lookup() -> None:
    """归案绑定的那条解析优先：同名的另一份解析（别的案子）不该被读进来。"""
    linked = _task("合同.pdf", markdown="## 本案合同正文", text="")
    _task("合同.pdf", markdown="## 别的案子的合同", text="")

    excerpt = facts_builder._material_markdown(_case(_material(filename="合同.pdf", task=linked)))

    assert "本案合同正文" in excerpt
    assert "别的案子的合同" not in excerpt


@pytest.mark.django_db
def test_linked_task_falls_back_to_text() -> None:
    """DeepSeek 后端的真实形态：markdown 为空、正文在 text。"""
    linked = _task("合同.pdf", markdown="", text="三、承包金 384277 元，应于 2026 年 5 月 8 日前缴交")

    excerpt = facts_builder._material_markdown(_case(_material(filename="合同.pdf", task=linked)))

    assert "384277" in excerpt
    assert excerpt.startswith("### 合同.pdf")


@pytest.mark.django_db
def test_filename_lookup_still_works_for_legacy_rows() -> None:
    """存量材料没有 FK，退回按文件名匹配——不能因为加了新口径就把老数据丢掉。"""
    _task("旧合同.pdf", markdown="历史解析正文", text="")

    excerpt = facts_builder._material_markdown(_case(_material(filename="旧合同.pdf")))

    assert "历史解析正文" in excerpt


@pytest.mark.django_db
def test_both_empty_is_skipped() -> None:
    linked = _task("合同.pdf", markdown="", text="   ")

    assert facts_builder._material_markdown(_case(_material(filename="合同.pdf", task=linked))) == ""


@pytest.mark.django_db
def test_excerpt_is_truncated() -> None:
    linked = _task("合同.pdf", markdown="", text="字" * (facts_builder.MATERIAL_EXCERPT_CHARS + 500))

    excerpt = facts_builder._material_markdown(_case(_material(filename="合同.pdf", task=linked)))

    assert len(excerpt) < facts_builder.MATERIAL_EXCERPT_CHARS + 100


def test_excerpt_keeps_clauses_beyond_the_head() -> None:
    """只截头部会漏条款：真机合同 2000 字之后才是承包金/滞纳金/解除条款。"""
    body = "首部" * 400 + "\n三、承包金 384277 元，应于 2026 年 5 月 8 日前缴交\n" + "无关段落" * 300

    excerpt = facts_builder._excerpt(body)

    assert "承包金 384277" in excerpt
    assert excerpt.startswith("首部")
    assert len(excerpt) <= facts_builder.MATERIAL_EXCERPT_CHARS


def test_excerpt_short_text_is_returned_whole() -> None:
    body = "短材料，承包金 100 元。"

    assert facts_builder._excerpt(body) == body


@pytest.mark.django_db
def test_dto_case_without_materials_falls_back_to_case_id() -> None:
    """起草链拿到的是 CaseDTO（不带 materials）：必须按 case_id 回查，否则整份材料静默消失。"""
    from apps.cases.models import Case
    from apps.cases.models.log import CaseLog
    from apps.cases.models.material import CaseMaterial
    from apps.organization.models import Lawyer

    case = Case.objects.create(name="DTO 回查案", yz_wid="")
    lawyer = Lawyer.objects.create(username="dto-lawyer", real_name="测试律师", license_no="TEST-002")
    log = CaseLog.objects.create(case=case, content="归案", actor=lawyer)
    attachment = CaseLogAttachmentStub.objects.create(log=log, original_filename="合同.pdf", file="x/合同.pdf")
    task = _task("合同.pdf", markdown="## 归案解析正文", text="")
    CaseMaterial.objects.create(case_id=case.id, type_name="客户提供材料", source_attachment=attachment, parsing_task=task)

    class _DtoCase:  # 只带 id：模拟 CaseDTO
        id = case.id

    excerpt = facts_builder._material_markdown(_DtoCase())

    assert "归案解析正文" in excerpt


def test_conflicting_registered_amount_is_dropped_not_fed() -> None:
    """案件登记的涉案金额与材料合计不一致时，不能把两套数字并列喂给模型。"""
    material = "被告拖欠承包款384277元、水费3250元、管理费16694元，合计404221元。"
    facts = {"涉案金额": "440000", "材料摘要": material}

    reconciled = facts_builder._reconcile_amounts(facts)

    assert "涉案金额" not in reconciled
    # 不补口径提示：多喂一个数字，模型就会把它当成本金再列一遍（真机 796,845 的来路）
    assert "口径提示" not in reconciled


def test_matching_registered_amount_is_kept() -> None:
    material = "承包款384277元、水费3250元、管理费16694元，合计404221元。"
    facts = {"涉案金额": "404221.00", "材料摘要": material}

    assert facts_builder._reconcile_amounts(facts)["涉案金额"] == "404221.00"


def test_no_totals_in_material_keeps_registered_amount() -> None:
    facts = {"涉案金额": "440000", "材料摘要": "合同约定按月付款。"}

    assert facts_builder._reconcile_amounts(facts)["涉案金额"] == "440000"
