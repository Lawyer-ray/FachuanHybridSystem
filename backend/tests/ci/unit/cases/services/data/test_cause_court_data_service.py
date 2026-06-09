"""Tests for cases.services.data.cause_court_data_service."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest

from apps.cases.services.data.cause_court_data_service import (
    CauseCourtDataCache,
    CauseCourtDataParser,
    CauseCourtDataService,
    CauseCourtDbProvider,
    CauseCourtJsonProvider,
)
from apps.core.exceptions import ValidationException


# ---------------------------------------------------------------------------
# CauseCourtDataParser tests
# ---------------------------------------------------------------------------


class TestCauseCourtDataParser:
    def setup_method(self):
        self.parser = CauseCourtDataParser()

    def test_flatten_tree_empty(self):
        result = self.parser.flatten_tree({})
        assert result == []

    def test_flatten_tree_single_node(self):
        data = {"name": "民事案由", "id": "1"}
        result = self.parser.flatten_tree(data)
        assert result == [{"id": "1", "name": "民事案由"}]

    def test_flatten_tree_nested(self):
        data = {
            "name": "root",
            "id": "0",
            "children": [
                {"name": "child1", "id": "1"},
                {
                    "name": "child2",
                    "id": "2",
                    "children": [{"name": "grandchild", "id": "2.1"}],
                },
            ],
        }
        result = self.parser.flatten_tree(data)
        names = [r["name"] for r in result]
        assert "root" in names
        assert "child1" in names
        assert "child2" in names
        assert "grandchild" in names

    def test_flatten_tree_skips_empty_name(self):
        data = {"name": "  ", "id": "1", "children": [{"name": "valid", "id": "2"}]}
        result = self.parser.flatten_tree(data)
        assert len(result) == 1
        assert result[0]["name"] == "valid"

    def test_flatten_tree_list_input(self):
        data = [{"name": "a", "id": "1"}, {"name": "b", "id": "2"}]
        result = self.parser.flatten_tree(data)
        assert len(result) == 2

    def test_filter_by_query_exact_match_first(self):
        items = [
            {"name": "合同纠纷", "id": "2"},
            {"name": "买卖合同纠纷", "id": "1"},
            {"name": "合同诈骗", "id": "3"},
        ]
        result = self.parser.filter_by_query(items, "合同纠纷")
        assert result[0]["name"] == "合同纠纷"

    def test_filter_by_query_starts_with_second(self):
        items = [
            {"name": "一般合同纠纷", "id": "1"},
            {"name": "合同", "id": "2"},
            {"name": "合同纠纷案", "id": "3"},
        ]
        result = self.parser.filter_by_query(items, "合同")
        assert result[0]["name"] == "合同"

    def test_filter_by_query_no_match(self):
        items = [{"name": "民事纠纷", "id": "1"}]
        result = self.parser.filter_by_query(items, "刑事")
        assert result == []


# ---------------------------------------------------------------------------
# CauseCourtDataCache tests
# ---------------------------------------------------------------------------


class TestCauseCourtDataCache:
    def test_load_json_file_not_found(self, tmp_path):
        cache = CauseCourtDataCache(data_dir=tmp_path)
        with pytest.raises(ValidationException):
            cache.load_json_file("nonexistent.json")

    def test_load_json_file_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")
        cache = CauseCourtDataCache(data_dir=tmp_path)
        with pytest.raises(ValidationException, match="数据文件格式错误"):
            cache.load_json_file("bad.json")

    def test_load_json_file_success(self, tmp_path):
        import json

        good_file = tmp_path / "good.json"
        good_file.write_text(json.dumps({"name": "test"}), encoding="utf-8")
        cache = CauseCourtDataCache(data_dir=tmp_path)
        result = cache.load_json_file("good.json")
        assert result == {"name": "test"}

    def test_load_json_file_caches_result(self, tmp_path):
        import json

        good_file = tmp_path / "cached.json"
        good_file.write_text(json.dumps({"key": "val"}), encoding="utf-8")
        cache = CauseCourtDataCache(data_dir=tmp_path)
        r1 = cache.load_json_file("cached.json")
        r2 = cache.load_json_file("cached.json")
        assert r1 is r2  # Same object due to lru_cache


# ---------------------------------------------------------------------------
# CauseCourtDbProvider tests
# ---------------------------------------------------------------------------


class TestCauseCourtDbProvider:
    def test_has_active_causes_success(self):
        mock_svc = MagicMock()
        mock_svc.has_active_causes_internal.return_value = True
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        assert provider.has_active_causes() is True

    def test_has_active_causes_exception_returns_false(self):
        mock_svc = MagicMock()
        mock_svc.has_active_causes_internal.side_effect = RuntimeError("db down")
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        assert provider.has_active_causes() is False

    def test_has_active_courts_exception_returns_false(self):
        mock_svc = MagicMock()
        mock_svc.has_active_courts_internal.side_effect = RuntimeError("db down")
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        assert provider.has_active_courts() is False

    def test_search_causes_delegates(self):
        mock_svc = MagicMock()
        mock_svc.search_causes_internal.return_value = [{"name": "test"}]
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        result = provider.search_causes("test", "civil", 10)
        assert result == [{"name": "test"}]

    def test_search_courts_delegates(self):
        mock_svc = MagicMock()
        mock_svc.search_courts_internal.return_value = [{"name": "court"}]
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        result = provider.search_courts("court", 5)
        assert result == [{"name": "court"}]

    def test_list_causes_by_parent_delegates(self):
        mock_svc = MagicMock()
        mock_svc.list_causes_by_parent_internal.return_value = []
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        result = provider.list_causes_by_parent(None)
        assert result == []


# ---------------------------------------------------------------------------
# CauseCourtJsonProvider tests
# ---------------------------------------------------------------------------


class TestCauseCourtJsonProvider:
    def setup_method(self):
        self.cache = MagicMock()
        self.parser = CauseCourtDataParser()
        self.file_map = {
            "civil": ["民事案由.json"],
            "criminal": ["刑事案由.json"],
            "bankruptcy": [],
        }
        self.provider = CauseCourtJsonProvider(
            cache=self.cache, parser=self.parser, case_type_file_map=self.file_map
        )

    def test_get_causes_by_type_bankruptcy_returns_empty(self):
        result = self.provider.get_causes_by_type("bankruptcy")
        assert result == []

    def test_get_causes_by_type_civil(self):
        self.cache.load_json_file.return_value = {
            "name": "root",
            "children": [{"name": "合同纠纷", "id": "1"}],
        }
        result = self.provider.get_causes_by_type("civil")
        assert len(result) >= 1

    def test_search_causes_with_case_type(self):
        self.cache.load_json_file.return_value = {
            "name": "root",
            "children": [
                {"name": "买卖合同纠纷", "id": "1"},
                {"name": "侵权纠纷", "id": "2"},
            ],
        }
        result = self.provider.search_causes("合同", "civil", 10)
        assert any("合同" in r["name"] for r in result)

    def test_search_causes_without_case_type(self):
        self.cache.load_json_file.return_value = {
            "name": "root",
            "children": [{"name": "测试案由", "id": "1"}],
        }
        result = self.provider.search_causes("测试", None, 10)
        assert len(result) >= 1

    def test_search_courts(self):
        self.cache.load_json_file.return_value = {
            "name": "root",
            "children": [{"name": "北京市第一中级人民法院", "id": "1"}],
        }
        result = self.provider.search_courts("北京", 5)
        assert any("北京" in r["name"] for r in result)


# ---------------------------------------------------------------------------
# CauseCourtDataService tests
# ---------------------------------------------------------------------------


class TestCauseCourtDataService:
    def setup_method(self):
        self.db_provider = MagicMock()
        self.json_provider = MagicMock()
        self.service = CauseCourtDataService(
            db_provider=self.db_provider,
            json_provider=self.json_provider,
        )

    def test_get_causes_by_type_invalid_raises(self):
        with pytest.raises(ValidationException, match="无效的案件类型"):
            self.service.get_causes_by_type("invalid_type")

    def test_get_causes_by_type_delegates_to_json(self):
        self.json_provider.get_causes_by_type.return_value = [{"name": "test"}]
        result = self.service.get_causes_by_type("civil")
        assert result == [{"name": "test"}]
        self.json_provider.get_causes_by_type.assert_called_once_with("civil")

    def test_search_causes_empty_query(self):
        assert self.service.search_causes("") == []
        assert self.service.search_causes("  ") == []

    def test_search_causes_uses_db_when_available(self):
        self.db_provider.has_active_causes.return_value = True
        self.db_provider.search_causes.return_value = [{"name": "db_result"}]
        result = self.service.search_causes("test", "civil", 10)
        assert result == [{"name": "db_result"}]
        self.db_provider.search_causes.assert_called_once()

    def test_search_causes_falls_back_to_json(self):
        self.db_provider.has_active_causes.return_value = False
        self.json_provider.search_causes.return_value = [{"name": "json_result"}]
        result = self.service.search_causes("test", "civil", 10)
        assert result == [{"name": "json_result"}]

    def test_search_courts_empty_query(self):
        assert self.service.search_courts("") == []
        assert self.service.search_courts("  ") == []

    def test_search_courts_uses_db_when_available(self):
        self.db_provider.has_active_courts.return_value = True
        self.db_provider.search_courts.return_value = [{"name": "db_court"}]
        result = self.service.search_courts("北京", 5)
        assert result == [{"name": "db_court"}]

    def test_search_courts_falls_back_to_json(self):
        self.db_provider.has_active_courts.return_value = False
        self.json_provider.search_courts.return_value = [{"name": "json_court"}]
        result = self.service.search_courts("北京", 5)
        assert result == [{"name": "json_court"}]

    def test_get_causes_by_parent_uses_db(self):
        self.db_provider.has_active_causes.return_value = True
        self.db_provider.list_causes_by_parent.return_value = [{"id": 1}]
        result = self.service.get_causes_by_parent(1)
        assert result == [{"id": 1}]

    def test_get_causes_by_parent_no_db_returns_empty(self):
        self.db_provider.has_active_causes.return_value = False
        result = self.service.get_causes_by_parent(None)
        assert result == []

    def test_flatten_tree_delegates(self):
        self.service._flatten_tree({"name": "test"})
