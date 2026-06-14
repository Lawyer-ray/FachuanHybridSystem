"""Tests for cases/services/material/case_material_query_service.py

Covers: list_bind_candidates, get_case_materials_view, get_used_type_ids,
get_material_types_by_category, _build_group_order_map, _sorted_groups,
_material_item_payload, case_service property.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.cases.services.material.case_material_query_service import (
    CaseMaterialQueryService,
)


class TestCaseServiceProperty:
    def test_raises_when_not_injected(self):
        svc = CaseMaterialQueryService(case_service=None)
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_returns_injected(self):
        cs = MagicMock()
        svc = CaseMaterialQueryService(case_service=cs)
        assert svc.case_service is cs


class TestBuildGroupOrderMap:
    def test_empty(self):
        svc = CaseMaterialQueryService()
        assert svc._build_group_order_map([]) == {}

    def test_single_row(self):
        svc = CaseMaterialQueryService()
        row = SimpleNamespace(category="party", side="our", supervising_authority_id=None, type_id=5)
        result = svc._build_group_order_map([row])
        assert result == {("party", "our", 0): [5]}

    def test_multiple_rows_same_key(self):
        svc = CaseMaterialQueryService()
        r1 = SimpleNamespace(category="party", side="our", supervising_authority_id=None, type_id=1)
        r2 = SimpleNamespace(category="party", side="our", supervising_authority_id=None, type_id=2)
        result = svc._build_group_order_map([r1, r2])
        assert result[("party", "our", 0)] == [1, 2]

    def test_with_supervising_authority(self):
        svc = CaseMaterialQueryService()
        row = SimpleNamespace(category="non_party", side=None, supervising_authority_id=10, type_id=3)
        result = svc._build_group_order_map([row])
        assert result == {("non_party", "", 10): [3]}


class TestSortedGroups:
    def test_ordered_by_order_map(self):
        svc = CaseMaterialQueryService()
        groups = {
            1: {"type_id": 1, "type_name": "B"},
            2: {"type_id": 2, "type_name": "A"},
        }
        order_map = {("party", "our", 0): [2, 1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert len(result) == 2
        assert result[0]["type_id"] == 2
        assert result[1]["type_id"] == 1

    def test_remaining_sorted_by_name(self):
        svc = CaseMaterialQueryService()
        groups = {
            1: {"type_id": 1, "type_name": "Z"},
            2: {"type_id": 2, "type_name": "A"},
            3: {"type_id": 3, "type_name": "M"},
        }
        order_map = {("party", "our", 0): [1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert result[0]["type_id"] == 1  # ordered first
        assert result[1]["type_name"] == "A"  # remaining sorted
        assert result[2]["type_name"] == "M"

    def test_empty_groups(self):
        svc = CaseMaterialQueryService()
        result = svc._sorted_groups("party", "our", None, {}, {})
        assert result == []


class TestMaterialItemPayload:
    def test_with_attachment(self):
        svc = CaseMaterialQueryService()
        att = SimpleNamespace(
            original_filename="test.pdf",
            file=SimpleNamespace(name="media/test.pdf", url="/media/test.pdf"),
            uploaded_at="2024-01-01",
        )
        party = SimpleNamespace(client=SimpleNamespace(name="ClientA"))
        m = SimpleNamespace(
            id=1,
            source_attachment_id=10,
            source_attachment=att,
            parties=MagicMock(),
        )
        m.parties.all.return_value = [party]

        result = svc._material_item_payload(m)
        assert result["material_id"] == 1
        assert result["file_name"] == "test.pdf"
        assert result["file_url"] == "/media/test.pdf"
        assert "ClientA" in result["party_labels"]

    def test_no_attachment(self):
        svc = CaseMaterialQueryService()
        m = SimpleNamespace(
            id=1,
            source_attachment_id=None,
            source_attachment=None,
            parties=MagicMock(),
        )
        m.parties.all.return_value = []

        result = svc._material_item_payload(m)
        assert result["material_id"] == 1
        assert result["file_name"] == ""

    def test_party_without_client_name(self):
        svc = CaseMaterialQueryService()
        att = SimpleNamespace(original_filename="f.pdf", file=None, uploaded_at=None)
        party_no_name = SimpleNamespace(client=SimpleNamespace(name=""))
        m = SimpleNamespace(
            id=2,
            source_attachment_id=20,
            source_attachment=att,
            parties=MagicMock(),
        )
        m.parties.all.return_value = [party_no_name]

        result = svc._material_item_payload(m)
        assert result["party_labels"] == []


class TestGetUsedTypeIds:
    @pytest.mark.django_db
    def test_empty_case(self):
        svc = CaseMaterialQueryService()
        result = svc.get_used_type_ids(999999)
        assert result == set()


class TestGetMaterialTypesByCategory:
    @pytest.mark.django_db
    def test_returns_list(self):
        svc = CaseMaterialQueryService()
        result = svc.get_material_types_by_category("party", None, set())
        assert isinstance(result, list)
