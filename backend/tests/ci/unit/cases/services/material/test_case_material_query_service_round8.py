"""case_material_query_service.py — round8 tests.

Covers 53 missing: list_bind_candidates, get_case_materials_view,
get_used_type_ids, get_material_types_by_category, _material_item_payload,
_sorted_groups, _build_group_order_map.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.cases.services.material.case_material_query_service import CaseMaterialQueryService


def _make_service(case_service=None):
    svc = CaseMaterialQueryService(case_service=case_service or MagicMock())
    return svc


# ── case_service property ──────────────────────────────────────────────


class TestCaseServiceProperty:
    def test_raises_when_none(self):
        svc = CaseMaterialQueryService(case_service=None)
        with pytest.raises(RuntimeError, match="未注入"):
            _ = svc.case_service

    def test_returns_injected(self):
        cs = MagicMock()
        svc = CaseMaterialQueryService(case_service=cs)
        assert svc.case_service is cs


# ── get_used_type_ids ──────────────────────────────────────────────────


class TestGetUsedTypeIds:
    @patch("apps.cases.services.material.case_material_query_service.CaseMaterial")
    def test_returns_set(self, MockCM):
        svc = _make_service()
        MockCM.objects.filter.return_value.values_list.return_value = [1, 2, 3]
        result = svc.get_used_type_ids(42)
        assert result == {1, 2, 3}
        MockCM.objects.filter.assert_called_once_with(case_id=42, type_id__isnull=False)


# ── get_material_types_by_category ─────────────────────────────────────


class TestGetMaterialTypesByCategory:
    @patch("apps.cases.services.material.case_material_query_service.CaseMaterialType")
    def test_basic_query(self, MockType):
        svc = _make_service()
        MockType.objects.filter.return_value.filter.return_value.order_by.return_value.values.return_value = [
            {"id": 1, "name": "Type A", "law_firm_id": None}
        ]
        result = svc.get_material_types_by_category("party", None, {1})
        assert len(result) == 1
        assert result[0]["id"] == 1


# ── list_bind_candidates ───────────────────────────────────────────────


class TestListBindCandidates:
    def test_basic_flow(self):
        svc = _make_service()
        svc._case_service.get_case.return_value = MagicMock()

        mock_att = MagicMock()
        mock_att.id = 10
        mock_att.original_filename = "test.pdf"
        mock_att.file.name = "files/test.pdf"
        mock_att.file.url = "/files/test.pdf"
        mock_att.uploaded_at = "2024-01-01"
        mock_att.log_id = 100
        mock_att.log.created_at = "2024-01-01"
        mock_att.log.actor.username = "user1"

        mock_material = MagicMock()
        mock_material.id = 20
        mock_material.category = "party"
        mock_material.type_id = 1
        mock_material.type_name = "合同"
        mock_material.side = "our"
        mock_material.supervising_authority_id = None
        mock_material.parties.values_list.return_value = [1, 2]
        mock_att.bound_material = mock_material

        qs = MagicMock()
        qs.__iter__ = MagicMock(return_value=iter([mock_att]))
        qs.__bool__ = MagicMock(return_value=True)
        qs.__len__ = MagicMock(return_value=1)

        with patch("apps.cases.services.material.case_material_query_service.CaseLogAttachment") as MockCLA:
            MockCLA.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs
            result = svc.list_bind_candidates(case_id=1)

        assert len(result) == 1
        assert result[0]["attachment_id"] == 10
        assert result[0]["material"]["type_id"] == 1

    def test_no_material(self):
        svc = _make_service()
        svc._case_service.get_case.return_value = MagicMock()

        mock_att = MagicMock()
        mock_att.id = 10
        mock_att.original_filename = "test.pdf"
        mock_att.file.name = "files/test.pdf"
        mock_att.file.url = ""
        mock_att.uploaded_at = "2024-01-01"
        mock_att.log_id = 100
        mock_att.log.created_at = None
        mock_att.log.actor = None
        mock_att.bound_material = None

        qs = MagicMock()
        qs.__iter__ = MagicMock(return_value=iter([mock_att]))
        qs.__bool__ = MagicMock(return_value=True)
        qs.__len__ = MagicMock(return_value=1)

        with patch("apps.cases.services.material.case_material_query_service.CaseLogAttachment") as MockCLA:
            MockCLA.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs
            result = svc.list_bind_candidates(case_id=1)

        assert len(result) == 1
        assert result[0]["material"] is None

    def test_empty_filename_fallback(self):
        svc = _make_service()
        svc._case_service.get_case.return_value = MagicMock()

        mock_att = MagicMock()
        mock_att.id = 10
        mock_att.original_filename = ""
        mock_att.file.name = "files/test.pdf"
        mock_att.file.url = ""
        mock_att.uploaded_at = None
        mock_att.log_id = 100
        mock_att.log.created_at = None
        mock_att.log.actor = None
        mock_att.bound_material = None

        qs = MagicMock()
        qs.__iter__ = MagicMock(return_value=iter([mock_att]))

        with patch("apps.cases.services.material.case_material_query_service.CaseLogAttachment") as MockCLA:
            MockCLA.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs
            result = svc.list_bind_candidates(case_id=1)

        assert result[0]["file_name"] == "test.pdf"


# ── _build_group_order_map ─────────────────────────────────────────────


class TestBuildGroupOrderMap:
    def test_basic(self):
        svc = _make_service()
        row = MagicMock()
        row.category = "party"
        row.side = "our"
        row.supervising_authority_id = None
        row.type_id = 5

        result = svc._build_group_order_map([row])
        assert ("party", "our", 0) in result
        assert result[("party", "our", 0)] == [5]

    def test_empty(self):
        svc = _make_service()
        assert svc._build_group_order_map([]) == {}

    def test_none_side(self):
        svc = _make_service()
        row = MagicMock()
        row.category = "non_party"
        row.side = None
        row.supervising_authority_id = 3
        row.type_id = 7

        result = svc._build_group_order_map([row])
        assert ("non_party", "", 3) in result


# ── _sorted_groups ─────────────────────────────────────────────────────


class TestSortedGroups:
    def test_ordered_and_remaining(self):
        svc = _make_service()
        groups = {
            1: {"type_id": 1, "type_name": "Z"},
            2: {"type_id": 2, "type_name": "A"},
        }
        order_map = {("party", "our", 0): [2, 1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert [g["type_id"] for g in result] == [2, 1]

    def test_remaining_sorted_alphabetically(self):
        svc = _make_service()
        groups = {
            1: {"type_id": 1, "type_name": "Zebra"},
            3: {"type_id": 3, "type_name": "Apple"},
        }
        order_map = {}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert [g["type_name"] for g in result] == ["Apple", "Zebra"]


# ── _material_item_payload ────────────────────────────────────────────


class TestMaterialItemPayload:
    def test_with_attachment(self):
        svc = _make_service()
        m = MagicMock()
        m.id = 1
        m.source_attachment_id = 10
        att = MagicMock()
        att.original_filename = "file.pdf"
        att.file.name = "files/file.pdf"
        att.file.url = "/url/file.pdf"
        att.uploaded_at = "2024-01-01"
        m.source_attachment = att
        p1 = MagicMock()
        p1.client.name = "Client A"
        p2 = MagicMock()
        p2.client = None
        m.parties.all.return_value = [p1, p2]

        result = svc._material_item_payload(m)
        assert result["material_id"] == 1
        assert result["attachment_id"] == 10
        assert "Client A" in result["party_labels"]

    def test_no_attachment(self):
        svc = _make_service()
        m = MagicMock()
        m.id = 2
        m.source_attachment_id = None
        m.source_attachment = None
        m.parties.all.return_value = []

        result = svc._material_item_payload(m)
        assert result["file_name"] == ""
        assert result["file_url"] == ""

    def test_attachment_no_filename_fallback(self):
        svc = _make_service()
        m = MagicMock()
        m.id = 3
        m.source_attachment_id = 20
        att = MagicMock()
        att.original_filename = ""
        att.file.name = "deep/path/file.pdf"
        att.file.url = ""
        att.uploaded_at = None
        m.source_attachment = att
        m.parties.all.return_value = []

        result = svc._material_item_payload(m)
        assert result["file_name"] == "file.pdf"


# ── get_case_materials_view ────────────────────────────────────────────


class TestCaseMaterialsView:
    def test_basic_view(self):
        svc = _make_service()
        case = MagicMock()
        case.id = 1
        case.parties.select_related.return_value.all.return_value = []
        case.supervising_authorities.all.return_value = []

        # Empty materials
        qs_mock = MagicMock()
        qs_mock.__iter__ = MagicMock(return_value=iter([]))

        group_order_qs = MagicMock()
        group_order_qs.__iter__ = MagicMock(return_value=iter([]))

        with patch("apps.cases.services.material.case_material_query_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_query_service.CaseMaterialGroupOrder") as MockGQ:
            svc._case_service.get_case.return_value = case
            MockCM.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs_mock
            MockGQ.objects.filter.return_value.select_related.return_value.order_by.return_value = group_order_qs

            result = svc.get_case_materials_view(case_id=1, user=None, org_access=None, perm_open_access=False)

        assert result["case_id"] == 1
        assert result["party"]["our"]["groups"] == []
        assert result["non_party"] == []

    def test_party_materials_grouped(self):
        svc = _make_service()
        case = MagicMock()
        case.id = 1
        case.parties.select_related.return_value.all.return_value = []
        case.supervising_authorities.all.return_value = []

        m = MagicMock()
        m.id = 1
        m.category = "party"
        m.side = "our"
        m.type_id = 10
        m.type_name = "合同"
        m.source_attachment = None
        m.source_attachment_id = None
        m.parties.all.return_value = []

        qs_mock = MagicMock()
        qs_mock.__iter__ = MagicMock(return_value=iter([m]))

        group_order_qs = MagicMock()
        group_order_qs.__iter__ = MagicMock(return_value=iter([]))

        with patch("apps.cases.services.material.case_material_query_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_query_service.CaseMaterialGroupOrder") as MockGQ:
            svc._case_service.get_case.return_value = case
            MockCM.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs_mock
            MockGQ.objects.filter.return_value.select_related.return_value.order_by.return_value = group_order_qs

            result = svc.get_case_materials_view(case_id=1)

        assert len(result["party"]["our"]["groups"]) == 1
        assert result["party"]["our"]["groups"][0]["type_name"] == "合同"

    def test_non_party_materials(self):
        svc = _make_service()
        case = MagicMock()
        case.id = 1
        case.parties.select_related.return_value.all.return_value = []

        auth = MagicMock()
        auth.id = 5
        auth.__str__ = MagicMock(return_value="天河法院")
        case.supervising_authorities.all.return_value = [auth]

        m = MagicMock()
        m.id = 2
        m.category = "non_party"
        m.side = None
        m.type_id = 20
        m.type_name = "传票"
        m.supervising_authority_id = 5
        m.source_attachment = None
        m.source_attachment_id = None
        m.parties.all.return_value = []

        qs_mock = MagicMock()
        qs_mock.__iter__ = MagicMock(return_value=iter([m]))

        group_order_qs = MagicMock()
        group_order_qs.__iter__ = MagicMock(return_value=iter([]))

        with patch("apps.cases.services.material.case_material_query_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_query_service.CaseMaterialGroupOrder") as MockGQ:
            svc._case_service.get_case.return_value = case
            MockCM.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs_mock
            MockGQ.objects.filter.return_value.select_related.return_value.order_by.return_value = group_order_qs

            result = svc.get_case_materials_view(case_id=1)

        assert len(result["non_party"]) == 1
        assert result["non_party"][0]["supervising_authority_id"] == 5

    def test_non_party_without_auth_skipped(self):
        svc = _make_service()
        case = MagicMock()
        case.id = 1
        case.parties.select_related.return_value.all.return_value = []
        case.supervising_authorities.all.return_value = []

        m = MagicMock()
        m.id = 3
        m.category = "non_party"
        m.side = None
        m.type_id = 30
        m.type_name = "文书"
        m.supervising_authority_id = None  # no auth → skip
        m.source_attachment = None
        m.source_attachment_id = None
        m.parties.all.return_value = []

        qs_mock = MagicMock()
        qs_mock.__iter__ = MagicMock(return_value=iter([m]))

        group_order_qs = MagicMock()
        group_order_qs.__iter__ = MagicMock(return_value=iter([]))

        with patch("apps.cases.services.material.case_material_query_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_query_service.CaseMaterialGroupOrder") as MockGQ:
            svc._case_service.get_case.return_value = case
            MockCM.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs_mock
            MockGQ.objects.filter.return_value.select_related.return_value.order_by.return_value = group_order_qs

            result = svc.get_case_materials_view(case_id=1)

        assert len(result["non_party"]) == 0

    def test_party_statuses_from_parties(self):
        svc = _make_service()
        case = MagicMock()
        case.id = 1

        p = MagicMock()
        p.legal_status = "plaintiff"
        p.get_legal_status_display.return_value = "原告"
        client = MagicMock()
        client.is_our_client = True
        p.client = client

        case.parties.select_related.return_value.all.return_value = [p]
        case.supervising_authorities.all.return_value = []

        qs_mock = MagicMock()
        qs_mock.__iter__ = MagicMock(return_value=iter([]))

        group_order_qs = MagicMock()
        group_order_qs.__iter__ = MagicMock(return_value=iter([]))

        with patch("apps.cases.services.material.case_material_query_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_query_service.CaseMaterialGroupOrder") as MockGQ:
            svc._case_service.get_case.return_value = case
            MockCM.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs_mock
            MockGQ.objects.filter.return_value.select_related.return_value.order_by.return_value = group_order_qs

            result = svc.get_case_materials_view(case_id=1)

        assert "原告" in result["party"]["our"]["legal_statuses"]

    def test_party_no_legal_status_skipped(self):
        svc = _make_service()
        case = MagicMock()
        case.id = 1

        p = MagicMock()
        p.legal_status = ""

        case.parties.select_related.return_value.all.return_value = [p]
        case.supervising_authorities.all.return_value = []

        qs_mock = MagicMock()
        qs_mock.__iter__ = MagicMock(return_value=iter([]))

        group_order_qs = MagicMock()
        group_order_qs.__iter__ = MagicMock(return_value=iter([]))

        with patch("apps.cases.services.material.case_material_query_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_query_service.CaseMaterialGroupOrder") as MockGQ:
            svc._case_service.get_case.return_value = case
            MockCM.objects.filter.return_value.select_related.return_value.prefetch_related.return_value.order_by.return_value = qs_mock
            MockGQ.objects.filter.return_value.select_related.return_value.order_by.return_value = group_order_qs

            result = svc.get_case_materials_view(case_id=1)

        assert result["party"]["our"]["legal_statuses"] == []
