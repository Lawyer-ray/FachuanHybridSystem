"""apps/core/services/cause_court_query_service.py 补充测试。

既有 test_cause_court_query_coverage.py 覆盖了 repository mock 的基础分支，
本文件补齐 search 非空路径与 list_causes_by_parent_internal 的两个分支
（顶层聚合 + 指定父节点），用链式 queryset mock 模拟 ORM 行为。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from apps.core.services.cause_court_query_service import CauseCourtQueryService


def _cause(cause_id: int, code: str, name: str, case_type: str = "civil", level: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=cause_id,
        code=code,
        name=name,
        case_type=case_type,
        level=level,
        full_path=f"/{name}",
    )


def _chainable_qs(
    items: list[Any],
    *,
    exists: bool = True,
) -> MagicMock:
    """构造支持 filter()/exclude()/exists()/order_by()/切片 的 queryset mock。"""
    qs = MagicMock()
    # filter/exclude 返回自身（链式），exists 可控
    qs.filter.return_value = qs
    qs.exclude.return_value = qs
    qs.exists.return_value = exists
    qs.order_by.return_value = items
    qs.__iter__ = MagicMock(return_value=iter(items))
    return qs


class TestGetCauseAncestorNames:
    def test_missing_cause_returns_empty(self) -> None:
        repo = MagicMock()
        repo.get_cause_by_id.return_value = None
        svc = CauseCourtQueryService(repository=repo)
        assert svc.get_cause_ancestor_names_internal(404) == []


class TestSearchCausesInternal:
    def _make(self, causes: list[Any]) -> tuple[CauseCourtQueryService, MagicMock]:
        repo = MagicMock()
        repo.search_causes.return_value = causes
        return CauseCourtQueryService(repository=repo), repo

    def test_returns_formatted_results(self) -> None:
        causes = [_cause(1, "M1", "买卖合同纠纷"), _cause(2, "M2", "借款合同纠纷")]
        svc, repo = self._make(causes)

        result = svc.search_causes_internal("合同", None, limit=10)

        assert len(result) == 2
        first = result[0]
        assert first["id"] == "M1"
        assert first["name"] == "买卖合同纠纷-M1"
        assert first["code"] == "M1"
        assert first["raw_name"] == "买卖合同纠纷"
        repo.search_causes.assert_called_once_with("合同", None)

    def test_strips_query_whitespace(self) -> None:
        svc, repo = self._make([])
        svc.search_causes_internal("  案由  ", None, 5)
        repo.search_causes.assert_called_once_with("案由", None)

    def test_execution_maps_to_all_types(self) -> None:
        svc, repo = self._make([])
        svc.search_causes_internal("q", "execution", 5)
        repo.search_causes.assert_called_once_with("q", ["civil", "criminal", "administrative"])

    def test_unknown_case_type_returns_empty(self) -> None:
        svc, repo = self._make([_cause(1, "X", "x")])
        result = svc.search_causes_internal("q", "not-a-type", 5)
        assert result == []
        repo.search_causes.assert_not_called()

    def test_limit_slices_queryset(self) -> None:
        causes = [_cause(i, f"C{i}", f"n{i}") for i in range(5)]
        svc, repo = self._make(causes)
        repo.search_causes.return_value = causes  # 真列表支持切片
        result = svc.search_causes_internal("q", None, 2)
        assert len(result) == 2


class TestSearchCourtsInternal:
    def test_returns_formatted_results(self) -> None:
        repo = MagicMock()
        repo.search_courts.return_value = [
            SimpleNamespace(code="粤01", name="广州市中级人民法院"),
        ]
        svc = CauseCourtQueryService(repository=repo)

        result = svc.search_courts_internal("广州", limit=5)

        assert result == [{"id": "粤01", "name": "广州市中级人民法院"}]
        repo.search_courts.assert_called_once_with("广州")

    def test_whitespace_query_returns_empty(self) -> None:
        repo = MagicMock()
        svc = CauseCourtQueryService(repository=repo)
        assert svc.search_courts_internal("   ", 5) == []
        repo.search_courts.assert_not_called()


class TestListCausesByParentTopLevel:
    def test_aggregates_top_level_by_case_type(self) -> None:
        """顶层无父节点（exists=True）时直接使用各 case_type 的顶层集合。"""
        civil_causes = [_cause(1, "A", "民事顶层", "civil")]
        criminal_causes = [_cause(2, "B", "刑事顶层", "criminal")]
        admin_causes = [_cause(3, "C", "行政顶层", "administrative")]

        repo = MagicMock()
        repo.get_causes_by_parent.side_effect = lambda parent_id, case_type=None: {
            "civil": _chainable_qs(civil_causes, exists=True),
            "criminal": _chainable_qs(criminal_causes, exists=True),
            "administrative": _chainable_qs(admin_causes, exists=True),
        }[case_type or "civil"]
        repo.get_parent_ids_with_children.return_value = {1}

        svc = CauseCourtQueryService(repository=repo)
        result = svc.list_causes_by_parent_internal(None)

        assert [r["id"] for r in result] == [1, 2, 3]
        by_id = {r["id"]: r for r in result}
        assert by_id[1]["has_children"] is True
        assert by_id[2]["has_children"] is False
        assert by_id[1]["case_type"] == "civil"
        assert by_id[1]["level"] == 1
        assert by_id[3]["full_path"] == "/行政顶层"
        # 批量子节点存在性只查一次
        repo.get_parent_ids_with_children.assert_called_once_with([1, 2, 3])

    def test_falls_back_to_cross_type_query_when_no_top_level(self) -> None:
        """某 case_type 无严格顶层（exists=False）时走跨类型回退分支。"""
        fallback_causes = [_cause(9, "Z", "回退节点", "civil")]
        repo = MagicMock()
        qs = _chainable_qs(fallback_causes, exists=False)
        # filter(parent__isnull=True).exists() -> False；二次 filter().exclude() 同一链
        repo.get_causes_by_parent.return_value = qs
        repo.get_parent_ids_with_children.return_value = set()

        svc = CauseCourtQueryService(repository=repo)
        result = svc.list_causes_by_parent_internal(None)

        assert len(result) == 3  # 三个 case_type 各回退一次，同一 mock
        assert all(r["id"] == 9 for r in result)
        # exists=False 走了 filter().exclude() 链
        qs.exclude.assert_called()


class TestListCausesByParent:
    def test_lists_children_of_parent(self) -> None:
        children = [
            _cause(11, "C11", "子案由1", "civil", level=2),
            _cause(12, "C12", "子案由2", "civil", level=2),
        ]
        repo = MagicMock()
        repo.get_causes_by_parent.return_value = _chainable_qs(children)
        repo.get_parent_ids_with_children.return_value = {11}

        svc = CauseCourtQueryService(repository=repo)
        result = svc.list_causes_by_parent_internal(10)

        assert [r["id"] for r in result] == [11, 12]
        repo.get_causes_by_parent.assert_called_once_with(10)
        repo.get_parent_ids_with_children.assert_called_once_with([11, 12])
        by_id = {r["id"]: r for r in result}
        assert by_id[11]["has_children"] is True
        assert by_id[12]["has_children"] is False
        assert by_id[12]["level"] == 2

    def test_parent_without_children(self) -> None:
        repo = MagicMock()
        repo.get_causes_by_parent.return_value = _chainable_qs([])
        repo.get_parent_ids_with_children.return_value = set()

        svc = CauseCourtQueryService(repository=repo)
        result = svc.list_causes_by_parent_internal(99)

        assert result == []
        repo.get_parent_ids_with_children.assert_called_once_with([])
