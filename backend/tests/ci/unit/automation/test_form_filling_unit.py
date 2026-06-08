"""form_filling_mixin.py 单元测试 — 纯逻辑函数。"""

from __future__ import annotations

import pytest


class TestExtractCourtKeywordGuarantee:

    @pytest.mark.parametrize("name,expected", [
        ("广州市天河区人民法院", "天河区"),
        ("北京市海淀区人民法院", "海淀区"),
        ("广东法院", "广东法院"),  # < 4 chars returns full
        ("广州互联网法院", "联网法院"),  # >= 4 chars returns last 4
        ("", "广东"),  # 空返回默认
    ])
    def test_extract_court_keyword(self, name, expected):
        from apps.automation.services.scraper.sites.guarantee.form_filling_mixin import GuaranteeFormFillingMixin
        result = GuaranteeFormFillingMixin._extract_court_keyword(name)
        assert expected in result or result == expected
