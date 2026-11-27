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
