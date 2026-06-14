"""Tests for cases/services/data/cause_court_data_service.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from apps.cases.services.data.cause_court_data_service import (
    CauseCourtDataCache,
    CauseCourtDataParser,
    CauseCourtDbProvider,
    CauseCourtJsonProvider,
    CauseCourtDataService,
)
from apps.core.exceptions import ValidationException


# ── CauseCourtDataParser ──────────────────────────────────────────────────────

class TestCauseCourtDataParser:

    def setup_method(self):
        self.parser = CauseCourtDataParser()

    def test_flatten_tree_basic(self):
        data = {"id": 1, "name": "Root", "children": [
            {"id": 2, "name": "Child A"},
            {"id": 3, "name": "Child B", "children": [
                {"id": 4, "name": "Grandchild"},
            ]},
        ]}
        result = self.parser.flatten_tree(data)
        names = [item["name"] for item in result]
        assert "Root" in names
        assert "Child A" in names
        assert "Child B" in names
        assert "Grandchild" in names

    def test_flatten_tree_list_input(self):
        data = [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
        ]
        result = self.parser.flatten_tree(data)
        assert len(result) == 2

    def test_flatten_tree_empty_children(self):
        data = {"id": 1, "name": "Root", "children": []}
        result = self.parser.flatten_tree(data)
        assert len(result) == 1

    def test_flatten_tree_no_name(self):
        data = {"id": 1, "children": [{"id": 2, "name": "Child"}]}
        result = self.parser.flatten_tree(data)
        assert len(result) == 1

    def test_flatten_tree_empty_name(self):
        data = {"id": 1, "name": "  ", "children": []}
        result = self.parser.flatten_tree(data)
        assert len(result) == 0

    def test_flatten_tree_none_children(self):
        data = {"id": 1, "name": "Root", "children": None}
        result = self.parser.flatten_tree(data)
        assert len(result) == 1

    def test_flatten_tree_with_existing_result(self):
        data = {"id": 1, "name": "A"}
        existing = [{"id": 0, "name": "Existing"}]
        result = self.parser.flatten_tree(data, existing)
        assert len(result) == 2

    def test_filter_by_query_exact_match(self):
        items = [
            {"name": "合同纠纷"},
            {"name": "买卖合同纠纷"},
            {"name": "侵权纠纷"},
        ]
        result = self.parser.filter_by_query(items, "合同纠纷")
        assert result[0]["name"] == "合同纠纷"  # exact match first

    def test_filter_by_query_prefix_match(self):
        items = [
            {"name": "ABC纠纷"},
            {"name": "A纠纷"},
        ]
        result = self.parser.filter_by_query(items, "A")
        # Both contain "A"; "A纠纷" starts with query so sorts first
        assert len(result) == 2

    def test_filter_by_query_no_match(self):
        items = [{"name": "合同纠纷"}]
        result = self.parser.filter_by_query(items, "侵权")
        assert len(result) == 0

    def test_filter_by_query_empty(self):
        result = self.parser.filter_by_query([], "query")
        assert result == []


# ── CauseCourtDataCache ───────────────────────────────────────────────────────

class TestCauseCourtDataCache:

    def test_load_json_file_not_found(self, tmp_path):
        cache = CauseCourtDataCache(tmp_path)
        with pytest.raises(ValidationException) as exc_info:
            cache.load_json_file("nonexistent.json")
        # The outer exception wraps the inner FILE_NOT_FOUND
        assert "FILE_NOT_FOUND" in str(exc_info.value.errors) or "FILE_LOAD_ERROR" in str(exc_info.value.code)

    def test_load_json_file_valid(self, tmp_path):
        data_file = tmp_path / "test.json"
        data_file.write_text('{"key": "value"}', encoding="utf-8")
        cache = CauseCourtDataCache(tmp_path)
        result = cache.load_json_file("test.json")
        assert result == {"key": "value"}

    def test_load_json_file_invalid_json(self, tmp_path):
        data_file = tmp_path / "bad.json"
        data_file.write_text("not json", encoding="utf-8")
        cache = CauseCourtDataCache(tmp_path)
        with pytest.raises(ValidationException) as exc_info:
            cache.load_json_file("bad.json")
        assert "JSON_PARSE_ERROR" in str(exc_info.value.code)


# ── CauseCourtDbProvider ──────────────────────────────────────────────────────

class TestCauseCourtDbProvider:

    def test_has_active_causes_true(self):
        mock_svc = MagicMock()
        mock_svc.has_active_causes_internal.return_value = True
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        assert provider.has_active_causes() is True

    def test_has_active_causes_exception(self):
        mock_svc = MagicMock()
        mock_svc.has_active_causes_internal.side_effect = Exception("db error")
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        assert provider.has_active_causes() is False

    def test_has_active_courts_true(self):
        mock_svc = MagicMock()
        mock_svc.has_active_courts_internal.return_value = True
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        assert provider.has_active_courts() is True

    def test_has_active_courts_exception(self):
        mock_svc = MagicMock()
        mock_svc.has_active_courts_internal.side_effect = Exception("db error")
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        assert provider.has_active_courts() is False

    def test_search_causes(self):
        mock_svc = MagicMock()
        mock_svc.search_causes_internal.return_value = [{"name": "test"}]
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        result = provider.search_causes("test", "civil", 10)
        assert result == [{"name": "test"}]

    def test_search_courts(self):
        mock_svc = MagicMock()
        mock_svc.search_courts_internal.return_value = [{"name": "court"}]
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        result = provider.search_courts("court", 10)
        assert result == [{"name": "court"}]

    def test_list_causes_by_parent(self):
        mock_svc = MagicMock()
        mock_svc.list_causes_by_parent_internal.return_value = [{"name": "child"}]
        provider = CauseCourtDbProvider(cause_court_query_service=mock_svc)
        result = provider.list_causes_by_parent(1)
        assert result == [{"name": "child"}]


# ── CauseCourtJsonProvider ────────────────────────────────────────────────────

class TestCauseCourtJsonProvider:

    def setup_method(self):
        self.mock_cache = MagicMock()
        self.parser = CauseCourtDataParser()
        self.file_map = {"civil": ["民事案由.json"], "bankruptcy": []}
        self.provider = CauseCourtJsonProvider(
            cache=self.mock_cache,
            parser=self.parser,
            case_type_file_map=self.file_map,
        )

    def test_get_causes_by_type_empty_map(self):
        result = self.provider.get_causes_by_type("bankruptcy")
        assert result == []

    def test_get_causes_by_type_success(self):
        self.mock_cache.load_json_file.return_value = {
            "name": "民事案由",
            "children": [{"id": 1, "name": "合同纠纷"}],
        }
        result = self.provider.get_causes_by_type("civil")
        assert len(result) >= 1

    def test_get_causes_by_type_file_error(self):
        self.mock_cache.load_json_file.side_effect = Exception("file error")
        result = self.provider.get_causes_by_type("civil")
        assert result == []

    def test_search_causes_with_type(self):
        self.mock_cache.load_json_file.return_value = {
            "name": "Root",
            "children": [
                {"id": 1, "name": "买卖合同纠纷"},
                {"id": 2, "name": "侵权纠纷"},
            ],
        }
        result = self.provider.search_causes("合同", "civil", 10)
        assert len(result) >= 1

    def test_search_causes_no_type(self):
        self.file_map = {
            "civil": ["民事案由.json"],
            "criminal": ["刑事案由.json"],
            "administrative": ["行政案由.json"],
        }
        self.provider = CauseCourtJsonProvider(
            cache=self.mock_cache,
            parser=self.parser,
            case_type_file_map=self.file_map,
        )
        self.mock_cache.load_json_file.return_value = {
            "name": "Root",
            "children": [{"id": 1, "name": "合同纠纷"}],
        }
        result = self.provider.search_causes("合同", None, 10)
        assert isinstance(result, list)

    def test_search_causes_no_type_with_error(self):
        self.file_map = {
            "civil": ["民事案由.json"],
            "criminal": ["刑事案由.json"],
            "administrative": ["行政案由.json"],
        }
        self.provider = CauseCourtJsonProvider(
            cache=self.mock_cache,
            parser=self.parser,
            case_type_file_map=self.file_map,
        )
        self.mock_cache.load_json_file.side_effect = Exception("fail")
        result = self.provider.search_causes("test", None, 10)
        assert isinstance(result, list)

    def test_search_courts_success(self):
        self.mock_cache.load_json_file.return_value = {
            "name": "法院",
            "children": [{"id": 1, "name": "北京市朝阳区人民法院"}],
        }
        result = self.provider.search_courts("朝阳", 10)
        assert len(result) >= 1

    def test_search_courts_error(self):
        self.mock_cache.load_json_file.side_effect = Exception("fail")
        with pytest.raises(Exception):
            self.provider.search_courts("test", 10)


# ── CauseCourtDataService ─────────────────────────────────────────────────────

class TestCauseCourtDataService:

    def setup_method(self):
        self.mock_db = MagicMock()
        self.mock_json = MagicMock()
        self.service = CauseCourtDataService(
            db_provider=self.mock_db,
            json_provider=self.mock_json,
        )

    def test_get_causes_by_type_invalid(self):
        with pytest.raises(ValidationException) as exc_info:
            self.service.get_causes_by_type("invalid_type")
        assert "INVALID_CASE_TYPE" in str(exc_info.value.code)

    def test_get_causes_by_type_valid(self):
        self.mock_json.get_causes_by_type.return_value = [{"name": "test"}]
        result = self.service.get_causes_by_type("civil")
        assert result == [{"name": "test"}]

    def test_search_causes_empty_query(self):
        assert self.service.search_causes("") == []
        assert self.service.search_causes("   ") == []
        assert self.service.search_causes(None) == []  # type: ignore[arg-type]

    def test_search_causes_db_active(self):
        self.mock_db.has_active_causes.return_value = True
        self.mock_db.search_causes.return_value = [{"name": "db_result"}]
        result = self.service.search_causes("合同", "civil", 10)
        assert result == [{"name": "db_result"}]

    def test_search_causes_db_inactive_fallback_json(self):
        self.mock_db.has_active_causes.return_value = False
        self.mock_json.search_causes.return_value = [{"name": "json_result"}]
        result = self.service.search_causes("合同", "civil", 10)
        assert result == [{"name": "json_result"}]

    def test_search_courts_empty_query(self):
        assert self.service.search_courts("") == []
        assert self.service.search_courts("   ") == []
        assert self.service.search_courts(None) == []  # type: ignore[arg-type]

    def test_search_courts_db_active(self):
        self.mock_db.has_active_courts.return_value = True
        self.mock_db.search_courts.return_value = [{"name": "court"}]
        result = self.service.search_courts("北京", 10)
        assert result == [{"name": "court"}]

    def test_search_courts_db_inactive(self):
        self.mock_db.has_active_courts.return_value = False
        self.mock_json.search_courts.return_value = [{"name": "court"}]
        result = self.service.search_courts("北京", 10)
        assert result == [{"name": "court"}]

    def test_get_causes_by_parent_db_active(self):
        self.mock_db.has_active_causes.return_value = True
        self.mock_db.list_causes_by_parent.return_value = [{"name": "child"}]
        result = self.service.get_causes_by_parent(1)
        assert result == [{"name": "child"}]

    def test_get_causes_by_parent_db_inactive(self):
        self.mock_db.has_active_causes.return_value = False
        result = self.service.get_causes_by_parent(1)
        assert result == []

    def test_get_causes_by_parent_exception(self):
        self.mock_db.has_active_causes.side_effect = Exception("db error")
        with pytest.raises(Exception):
            self.service.get_causes_by_parent(1)

    def test_flatten_tree_delegates(self):
        data = {"id": 1, "name": "Root"}
        result = self.service._flatten_tree(data)
        assert len(result) == 1

    def test_get_cause_by_id(self):
        mock_cause = {"id": 1, "name": "合同纠纷"}
        with patch("apps.core.interfaces.ServiceLocator") as mock_sl:
            mock_sl.get_cause_court_query_service.return_value.get_cause_by_id_internal.return_value = mock_cause
            result = self.service.get_cause_by_id(1)
        assert result == mock_cause

    def test_property_lazy_loads(self):
        svc = CauseCourtDataService()
        # Verify properties return non-None when accessed
        assert svc.parser is not None
        # cache requires data_dir, just verify it doesn't crash
        assert svc.cache is not None
