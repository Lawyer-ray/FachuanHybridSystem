"""证件到期日：正则解析 + 状态判定 + LLM 交叉校验的回归测试。

背景（2026-11-06 实测）：身份证「有效期限」是起止区间，旧正则在下列形态下会
把**签发日**当成到期日，导致 2045 年到期的证件被判成 2025 年已过期（假告警）：
- 年月日格式：2025年11月07日至2045年11月07日
- OCR 丢分隔符：2025.11.072045.11.07
- OCR 把区间拆成两行
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.client.services.identity_expiry_service import (
    STATUS_EXPIRED,
    STATUS_EXPIRING,
    STATUS_MISSING,
    STATUS_OK,
    aggregate_client_status,
    evaluate_expiry,
    summarize_counts,
)

pytestmark = pytest.mark.django_db


class TestExpiryRegexParsing:
    """正则必须取区间**末日**，绝不能拿签发日冒充到期日。"""

    @pytest.fixture()
    def svc(self):
        from apps.client.services.identity_extraction import IdentityExtractionService

        return IdentityExtractionService()

    @pytest.mark.parametrize(
        "lines,expected",
        [
            (["有效期限2025.11.07-2045.11.07"], "2045-11-07"),
            (["有效期限 2025.11.07 - 2045.11.07"], "2045-11-07"),
            (["有效期限2025/11/07-2045/11/07"], "2045-11-07"),
            (["有效期限2025.11.07至2045.11.07"], "2045-11-07"),
            (["有效期限2025.11.07—2045.11.07"], "2045-11-07"),
            # 年月日格式（旧实现错拿签发日 2025-11-07）
            (["有效期限2025年11月07日至2045年11月07日"], "2045-11-07"),
            (["有效期限2025年11月7日至2045年11月7日"], "2045-11-07"),
            # OCR 丢分隔符（旧实现错拿 2025-11-07）
            (["有效期限2025.11.072045.11.07"], "2045-11-07"),
            # OCR 断行（旧实现错拿 2025-11-07）
            (["有效期限2025.11.07-", "2045.11.07"], "2045-11-07"),
            (["有效期限", "2025.11.07-2045.11.07"], "2045-11-07"),
            # 长期
            (["有效期限2020.03.22-长期"], "2099-12-31"),
            # 明确「有效期至」单日期
            (["有效期至 2045-11-07"], "2045-11-07"),
        ],
    )
    def test_expiry_range_returns_end_date(self, svc, lines, expected):
        assert svc._extract_expiry_date(lines) == expected

    def test_single_issue_date_is_not_trusted(self, svc):
        """只有签发日、没有到期日时宁可返回 None，也不能误报过期。"""
        assert svc._extract_expiry_date(["有效期限2025.11.07"]) is None


class TestEvaluateExpiry:
    TODAY = date(2026, 11, 6)

    def test_expired(self):
        st = evaluate_expiry(date(2025, 1, 1), self.TODAY)
        assert st.status == STATUS_EXPIRED
        assert st.needs_attention

    def test_expiring_within_30_days(self):
        st = evaluate_expiry(date(2026, 11, 20), self.TODAY)
        assert st.status == STATUS_EXPIRING
        assert st.days_left == 14

    def test_ok_far_future(self):
        st = evaluate_expiry(date(2045, 11, 7), self.TODAY)
        assert st.status == STATUS_OK
        assert not st.needs_attention

    def test_missing_when_no_date(self):
        assert evaluate_expiry(None, self.TODAY).status == STATUS_MISSING

    def test_missing_when_no_file(self):
        """没有文件时即使有日期也算缺失——无法核验。"""
        st = evaluate_expiry(date(2045, 11, 7), self.TODAY, has_file=False)
        assert st.status == STATUS_MISSING

    def test_long_term_not_flagged(self):
        assert evaluate_expiry(date(2099, 12, 31), self.TODAY).status == STATUS_OK


class TestAggregateClientStatus:
    TODAY = date(2026, 11, 6)

    def test_no_docs_is_missing(self):
        assert aggregate_client_status([], self.TODAY).status == STATUS_MISSING

    def test_expired_wins_over_others(self):
        docs = [(date(2025, 1, 1), True), (date(2045, 1, 1), True)]
        assert aggregate_client_status(docs, self.TODAY).status == STATUS_EXPIRED

    def test_expiring_picks_most_urgent(self):
        docs = [(date(2026, 12, 1), True), (date(2026, 11, 10), True)]
        st = aggregate_client_status(docs, self.TODAY)
        assert st.status == STATUS_EXPIRING
        assert st.days_left == 4

    def test_summarize_counts(self):
        docs = [(date(2025, 1, 1), True), (date(2045, 1, 1), True), (None, False)]
        statuses = [aggregate_client_status([d], self.TODAY) for d in docs]
        counts = summarize_counts(statuses)
        assert counts[STATUS_EXPIRED] == 1
        assert counts[STATUS_OK] == 1
        assert counts[STATUS_MISSING] == 1


class TestLLMCrossCheck:
    """身份证类证件必须同时跑 LLM，且以 LLM 的到期日为准。"""

    def test_id_card_forces_llm_even_when_key_field_hit(self):
        from apps.client.services.identity_extraction import extraction_service as mod

        assert "id_card" in mod._DOC_TYPES_WITH_EXPIRY_RANGE
        assert "legal_rep_id_card" in mod._DOC_TYPES_WITH_EXPIRY_RANGE
        # 营业执照不需要区间校验
        assert "business_license" not in mod._DOC_TYPES_WITH_EXPIRY_RANGE

    def test_llm_expiry_overrides_wrong_regex(self):
        """正则给出签发日、LLM 给出到期日时，结果必须是到期日。"""
        from unittest.mock import patch

        from apps.client.services.identity_extraction import IdentityExtractionService

        svc = IdentityExtractionService()
        regex_data = {"id_number": "440681199708253000", "expiry_date": "2025-11-07", "name": "测试"}
        llm_data = {"id_number": "440681199708253000", "expiry_date": "2045-11-07", "name": "测试"}

        with (
            patch.object(svc, "_ocr_extract", return_value="有效期限2025年11月07日至2045年11月07日"),
            patch.object(svc, "_resolve_doc_type", return_value="id_card"),
            patch.object(svc, "_extract_by_rules", return_value=regex_data),
            patch.object(svc, "_llm_extract", return_value=llm_data),
        ):
            result = svc.extract(b"fake", "id_card", model="any-model")

        assert result.extracted_data["expiry_date"] == "2045-11-07"
        assert result.extraction_method == "ocr_regex_llm"
