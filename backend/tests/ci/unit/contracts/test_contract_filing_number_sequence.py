"""合同建档编号序号生成回归测试。

覆盖 advisory lock + 取最大后缀方案的核心语义：
- 连续建档序号递增；
- 删除中间序号后不再与存量编号冲突（旧 count+1 方案的卡死缺陷）；
- 脏数据后缀与其他年份编号不影响当年序号。
"""

from __future__ import annotations

import pytest

from apps.contracts.services.assignment.filing_number_service import FilingNumberService
from apps.testing.factories import ContractFactory


@pytest.mark.django_db
class TestContractFilingSequence:
    def test_sequence_increments_across_consecutive_filings(self, db):
        """连续两次建档（模拟工作流落库后）序号应递增。"""
        svc = FilingNumberService()

        first = svc.generate_contract_filing_number(contract_id=1, case_type="civil", created_year=2026)
        ContractFactory(filing_number=first)
        second = svc.generate_contract_filing_number(contract_id=2, case_type="civil", created_year=2026)

        assert first == "2026_民商事_HT_1"
        assert second == "2026_民商事_HT_2"

    def test_sequence_after_deleted_gap_does_not_collide(self, db):
        """存量 1、3（2 已删除场景）：新序号应为 4，而非旧 count+1 的 3（与存量冲突）。"""
        ContractFactory(filing_number="2026_民商事_HT_1")
        ContractFactory(filing_number="2026_民商事_HT_3")

        svc = FilingNumberService()

        assert svc._get_next_contract_sequence(2026) == 4

    def test_sequence_ignores_dirty_suffix_and_other_years(self, db):
        """非数字后缀的脏数据与其他年份编号不应参与当年最大值计算，也不应报错。"""
        ContractFactory(filing_number="2026_民商事_HT_7")
        ContractFactory(filing_number="2026_民商事_HT_补录")  # 脏数据后缀
        ContractFactory(filing_number="2025_民商事_HT_99")  # 其他年份

        svc = FilingNumberService()

        assert svc._get_next_contract_sequence(2026) == 8
