"""模板类文书过滤单测 — 「送识别前排除无期限的模板」。

口径（业务确认 2026-11-14）：法院一次送达常带 9~12 份文书，其中模板类
（廉政监督卡 / 送达地址确认书 / 退费申请书 / 诉讼权利义务告知书…）结构固定、
从不含期限，送识别只是白烧一次 LLM。默认全部识别，只排除这些。

**反向守住**同样重要：含保全到期日的「告知书」、举证通知书、交费通知书
这类**名字相似但含期限**的实体文书绝不能被误杀。
"""

from __future__ import annotations

import pytest

from apps.document_recognition.services.document_template_filter import (
    filter_recognizable_documents,
    is_template_document,
)


class TestTemplatesAreExcluded:
    @pytest.mark.parametrize(
        "name",
        [
            "廉政监督卡（张某诉李某案）_20261106收.pdf",
            "廉政监督卡.pdf",
            "送达地址确认书（张某诉李某案）_20261106收.pdf",
            "退费申请书（张某诉李某案）_20261106收.pdf",
            "诉讼权利义务告知书（张某诉李某案）_20261106收.pdf",
            "zdqz民事诉讼风险提示书（张某诉李某案）_20261106收.pdf",
            "司法作风监督卡.pdf",
        ],
    )
    def test_template_detected(self, name: str) -> None:
        assert is_template_document(name) is True


class TestSubstantiveDocumentsAreKept:
    """实体文书一律保留——宁可多烧一次 LLM，也不漏掉真期限。"""

    @pytest.mark.parametrize(
        "name",
        [
            "传票（某案）_20261103收.pdf",
            "民事判决书（某案）_20261106收.pdf",
            "民事裁定书（某案）_20261027收.pdf",
            "执行裁定书（某案）_20261106收.pdf",
            # 关键：名字像模板但含保全到期日，绝不能过滤
            "告知书（某执行案件）_2026XXXX收.pdf",
            "举证通知书（某案）_20261009收.pdf",
            "诉讼费用交费通知书（某案）_20261103收.pdf",
            "受理案件通知书（某案）_20261009收.pdf",
            "诉讼材料提交告知书（某案）_20261009收.pdf",
        ],
    )
    def test_substantive_kept(self, name: str) -> None:
        assert is_template_document(name) is False

    def test_empty_and_non_string_safe(self) -> None:
        assert is_template_document("") is False
        assert is_template_document(None) is False  # type: ignore[arg-type]


class TestFilterSplit:
    def test_splits_and_reports_skipped(self) -> None:
        names = ["廉政监督卡.pdf", "传票.pdf", "退费申请书.pdf", "判决书.pdf"]
        keep, skipped = filter_recognizable_documents(names)
        assert keep == ["传票.pdf", "判决书.pdf"]
        assert skipped == ["廉政监督卡.pdf", "退费申请书.pdf"]
