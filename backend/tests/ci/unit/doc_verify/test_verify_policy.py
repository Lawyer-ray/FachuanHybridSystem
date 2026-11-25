"""策略：哪些文书默认要求回传核对。

高风险四类靠**子串**命中——卷宗里的写法不统一（前缀、后缀、版本号），
要求精确相等等于让策略在真实数据上永远不命中。
"""

from __future__ import annotations

import pytest

from apps.doc_verify.services.verify.policy import HIGH_RISK_DOC_TYPES, should_verify


class TestHighRiskDocTypes:
    def test_frozen_contract_holds_the_four_types(self) -> None:
        assert HIGH_RISK_DOC_TYPES == (
            "起诉状",
            "授权委托书",
            "送达地址确认书",
            "退费账户确认书",
        )

    @pytest.mark.parametrize("doc_type", HIGH_RISK_DOC_TYPES)
    def test_exact_names_require_verification(self, doc_type: str) -> None:
        assert should_verify(doc_type) is True


class TestShouldVerify:
    @pytest.mark.parametrize(
        "doc_type",
        [
            "民事起诉状（一审）",
            "起诉状-补充",
            "王某某诉李某某_起诉状_定稿",
            "授权委托书（含送达地址）",
            "送达地址确认书（新版）",
            "退费账户确认书扫描件",
        ],
    )
    def test_tolerates_volume_naming_noise(self, doc_type: str) -> None:
        """名字前后带卷宗惯用前后缀，策略照样命中。"""
        assert should_verify(doc_type) is True

    def test_leading_and_trailing_spaces_do_not_block_match(self) -> None:
        assert should_verify("  起诉状  ") is True

    @pytest.mark.parametrize("doc_type", ["证据清单", "答辩状", "民事判决书", "执行申请书"])
    def test_other_documents_are_not_required_by_default(self, doc_type: str) -> None:
        assert should_verify(doc_type) is False

    @pytest.mark.parametrize("doc_type", ["", "   "])
    def test_empty_name_is_not_required(self, doc_type: str) -> None:
        """空名字不是「高风险」，也不能因为空串被 any() 误判成命中。"""
        assert should_verify(doc_type) is False
