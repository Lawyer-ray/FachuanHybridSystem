"""材料摘录必须能从 `text` 回退——否则材料会静默缺席起草提示词。

真机基线（docs/analysis/legal-doc-generation-2026-11-26/07 §D2）：
- DeepSeek OCR 后端只写 `text`，`ParsedDocument.markdown` 恒为 None；
- 开发库 84 条 completed 解析任务里 35 条 `markdown` 为空（backend_used=mineru）。
`_material_markdown` 原先只读 `markdown`，于是这些材料被**静默丢弃**：模型拿不到合同，
成稿里也看不出少了一整份证据。
"""

from __future__ import annotations

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


@pytest.fixture()
def one_material(monkeypatch: pytest.MonkeyPatch) -> Any:
    """只给一个材料文件名，避免依赖 Case 实体（本用例只测「取值口径」）。"""
    monkeypatch.setattr(facts_builder, "_material_filenames", lambda _case: ["合同.pdf"])
    return object()


@pytest.mark.django_db
def test_markdown_preferred_when_present(one_material: Any) -> None:
    _task("合同.pdf", markdown="## 合同正文", text="纯文本正文")

    excerpt = facts_builder._material_markdown(one_material)

    assert "## 合同正文" in excerpt
    assert "纯文本正文" not in excerpt


@pytest.mark.django_db
def test_falls_back_to_text_when_markdown_empty(one_material: Any) -> None:
    """DeepSeek 后端的真实形态：markdown 为空、正文在 text。"""
    _task("合同.pdf", markdown="", text="三、承包金 384277 元，应于 2026 年 5 月 8 日前缴交")

    excerpt = facts_builder._material_markdown(one_material)

    assert "384277" in excerpt
    assert excerpt.startswith("### 合同.pdf")


@pytest.mark.django_db
def test_both_empty_is_skipped(one_material: Any) -> None:
    _task("合同.pdf", markdown="", text="   ")

    assert facts_builder._material_markdown(one_material) == ""


@pytest.mark.django_db
def test_excerpt_is_truncated(one_material: Any) -> None:
    _task("合同.pdf", markdown="", text="字" * (facts_builder.MATERIAL_EXCERPT_CHARS + 500))

    excerpt = facts_builder._material_markdown(one_material)

    assert len(excerpt) < facts_builder.MATERIAL_EXCERPT_CHARS + 100
