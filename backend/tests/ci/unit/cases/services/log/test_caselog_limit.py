"""/logs limit/offset 分页语义单测（无界全量物化修复的行为锚点）。

回归语义：不传 case_id 也不再全表物化；limit/offset 正确切片（按 -created_at）。
"""

from __future__ import annotations

import pytest

from apps.cases.services.log.caselog_service import CaseLogService
from apps.testing.factories import CaseFactory, CaseLogFactory


@pytest.mark.django_db
class TestListLogsPagination:
    def _make_logs(self, n: int = 5):
        case = CaseFactory()
        for _ in range(n):
            CaseLogFactory(case=case)
        return case

    def test_limit_respected(self):
        self._make_logs(5)
        svc = CaseLogService()
        result = svc.list_logs_for_serialization(case_id=None, user=None, perm_open_access=True, limit=2)
        assert len(result) == 2

    def test_offset_pages_through(self):
        self._make_logs(5)
        svc = CaseLogService()
        page1 = svc.list_logs_for_serialization(case_id=None, user=None, perm_open_access=True, limit=2, offset=0)
        page2 = svc.list_logs_for_serialization(case_id=None, user=None, perm_open_access=True, limit=2, offset=2)
        ids1 = {log.id for log in page1}
        ids2 = {log.id for log in page2}
        assert len(page1) == 2 and len(page2) == 2
        assert not (ids1 & ids2), "分页窗口不应重叠"

    def test_default_is_unlimited_for_backcompat_callers(self):
        """limit=None（默认）保持全量——非 API 调用方行为不变。"""
        self._make_logs(3)
        svc = CaseLogService()
        result = svc.list_logs_for_serialization(case_id=None, user=None, perm_open_access=True)
        assert len(result) == 3
