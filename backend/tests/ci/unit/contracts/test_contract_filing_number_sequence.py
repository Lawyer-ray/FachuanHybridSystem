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


@pytest.mark.django_db(transaction=True)
class TestAssignFilingNumberLockCoverage:
    """assign_filing_number：锁必须覆盖「取号 + 写回」全程。

    原实现（generate_* 内部 atomic 取号 → 返回后调用方另起事务 save）
    在并发下会让两个请求拿到同一序号并撞 unique=True。本组用例锁定新语义。
    """

    def test_assign_persists_and_skips_when_already_set(self) -> None:
        svc = FilingNumberService()
        contract = ContractFactory(filing_number=None, case_type="civil")

        first = svc.assign_filing_number(contract, created_year=2031)

        assert first == "2031_民商事_HT_1"
        contract.refresh_from_db()
        assert contract.filing_number == first

        # 已有编号时不重新分配（幂等）
        again = svc.assign_filing_number(contract, created_year=2031)
        assert again == first

    def test_concurrent_assign_yields_distinct_numbers(self) -> None:
        """20 个线程并发分配：不得出现重复编号，也不得抛唯一约束错。"""
        import threading

        svc = FilingNumberService()
        contracts = [ContractFactory(filing_number=None, case_type="civil") for _ in range(20)]
        results: list[str] = []
        errors: list[Exception] = []
        barrier = threading.Barrier(len(contracts))

        def _worker(c) -> None:
            barrier.wait()  # 尽量同时冲进去，放大并发窗口
            try:
                results.append(svc.assign_filing_number(c, created_year=2032))
            except Exception as exc:  # noqa: BLE001 - 测试要捕获任何异常
                errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(c,)) for c in contracts]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发分配抛异常（锁未覆盖写回时会撞 unique）: {errors[:3]}"
        assert len(results) == len(contracts)
        assert len(set(results)) == len(results), f"出现重复编号: {sorted(results)}"
