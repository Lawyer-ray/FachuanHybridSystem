"""filing_steps.py 单元测试 — 纯逻辑函数。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class TestExtractCourtKeyword:

    @pytest.mark.parametrize("name,expected", [
        ("广州市天河区人民法院", "天河区"),
        ("北京市海淀区人民法院", "海淀区"),
        ("深圳市南山区人民法院", "南山区"),
        ("某县人民法院", "某县"),
        ("广州互联网法院", "互联网法"),  # 无区/县时返回原名
    ])
    def test_extract_court_keyword(self, name, expected):
        from apps.automation.services.scraper.sites.court_zxfw_filing.filing_steps import FilingStepsMixin
        result = FilingStepsMixin._extract_court_keyword(name)
        assert expected in result


class TestInferUploadSlotByText:

    def test_civil_slot_0_complaint(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.filing_steps import FilingStepsMixin
        mixin = FilingStepsMixin.__new__(FilingStepsMixin)
        mixin.CIVIL_UPLOAD_SLOT_KEYWORDS = [
            ("0", ("民事起诉状", "起诉状")),
            ("1", ("身份证明", "身份证")),
        ]
        mixin.EXEC_UPLOAD_SLOT_KEYWORDS = []
        result = mixin._infer_upload_slot_by_text(
            container_text="民事起诉状", is_execution=False
        )
        assert result == "0"

    def test_civil_slot_1_identity(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.filing_steps import FilingStepsMixin
        mixin = FilingStepsMixin.__new__(FilingStepsMixin)
        mixin.CIVIL_UPLOAD_SLOT_KEYWORDS = [
            ("0", ("民事起诉状",)),
            ("1", ("身份证明", "身份证")),
        ]
        mixin.EXEC_UPLOAD_SLOT_KEYWORDS = []
        result = mixin._infer_upload_slot_by_text(
            container_text="身份证 明材料", is_execution=False
        )
        assert result == "1"

    def test_empty_text_returns_none(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.filing_steps import FilingStepsMixin
        mixin = FilingStepsMixin.__new__(FilingStepsMixin)
        mixin.CIVIL_UPLOAD_SLOT_KEYWORDS = []
        mixin.EXEC_UPLOAD_SLOT_KEYWORDS = []
        assert mixin._infer_upload_slot_by_text(container_text="", is_execution=False) is None

    def test_no_match_returns_none(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.filing_steps import FilingStepsMixin
        mixin = FilingStepsMixin.__new__(FilingStepsMixin)
        mixin.CIVIL_UPLOAD_SLOT_KEYWORDS = [("0", ("起诉状",))]
        mixin.EXEC_UPLOAD_SLOT_KEYWORDS = []
        assert mixin._infer_upload_slot_by_text(
            container_text="其他材料", is_execution=False
        ) is None

    def test_exec_uses_exec_keywords(self):
        from apps.automation.services.scraper.sites.court_zxfw_filing.filing_steps import FilingStepsMixin
        mixin = FilingStepsMixin.__new__(FilingStepsMixin)
        mixin.CIVIL_UPLOAD_SLOT_KEYWORDS = []
        mixin.EXEC_UPLOAD_SLOT_KEYWORDS = [("0", ("执行申请书",))]
        result = mixin._infer_upload_slot_by_text(
            container_text="执行申请书", is_execution=True
        )
        assert result == "0"
