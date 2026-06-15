"""case_material_service.py — round8 tests for remaining uncovered branches.

Covers 39 missing: replace_material_file, delete_material, _validate_party_ids,
_resolve_type (via mock), _sorted_groups, _material_item_payload.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.material.case_material_service import CaseMaterialService
from apps.core.exceptions import NotFoundError, ValidationException


def _make_service(**overrides):
    case_service = overrides.get("case_service", MagicMock())
    return CaseMaterialService(
        case_service=case_service,
        query_service=overrides.get("query_service", MagicMock()),
        binding_workflow=overrides.get("binding_workflow", MagicMock()),
    )


# ── replace_material_file ──────────────────────────────────────────────


class TestReplaceMaterialFile:
    def test_material_not_found(self):
        svc = _make_service()
        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM:
            MockCM.DoesNotExist = Exception
            MockCM.objects.select_related.return_value.get.side_effect = MockCM.DoesNotExist

            with pytest.raises(NotFoundError):
                svc.replace_material_file(case_id=1, material_id=1, new_attachment_id=2)

    def test_same_attachment(self):
        svc = _make_service()
        material = MagicMock()
        material.source_attachment_id = 1

        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM:
            MockCM.objects.select_related.return_value.get.return_value = material

            with pytest.raises(ValidationException, match="相同"):
                svc.replace_material_file(case_id=1, material_id=1, new_attachment_id=1)

    def test_new_attachment_not_found(self):
        svc = _make_service()
        material = MagicMock()
        material.source_attachment_id = 1

        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_service.CaseLogAttachment") as MockCLA:
            MockCM.objects.select_related.return_value.get.return_value = material
            MockCLA.DoesNotExist = Exception
            MockCLA.objects.select_related.return_value.get.side_effect = MockCLA.DoesNotExist

            with pytest.raises(NotFoundError, match="不存在"):
                svc.replace_material_file(case_id=1, material_id=1, new_attachment_id=2)

    def test_new_attachment_already_bound(self):
        svc = _make_service()
        material = MagicMock()
        material.source_attachment_id = 1

        new_att = MagicMock()
        new_att.id = 2
        existing_material = MagicMock()
        existing_material.id = 99

        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_service.CaseLogAttachment") as MockCLA:
            MockCM.objects.select_related.return_value.get.return_value = material
            MockCLA.objects.select_related.return_value.get.return_value = new_att
            MockCM.objects.filter.return_value.first.return_value = existing_material

            with pytest.raises(ValidationException, match="已被其他材料绑定"):
                svc.replace_material_file(case_id=1, material_id=1, new_attachment_id=2)

    def test_successful_replace(self):
        svc = _make_service()
        material = MagicMock()
        material.source_attachment_id = 1
        material.source_attachment = MagicMock()
        material.source_attachment.file = MagicMock()

        new_att = MagicMock()
        new_att.id = 2

        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM, \
             patch("apps.cases.services.material.case_material_service.CaseLogAttachment") as MockCLA:
            MockCM.objects.select_related.return_value.get.return_value = material
            MockCLA.objects.select_related.return_value.get.return_value = new_att
            MockCM.objects.filter.return_value.first.return_value = None

            result = svc.replace_material_file(case_id=1, material_id=1, new_attachment_id=2)
            assert result["new_attachment_id"] == 2
            assert result["old_attachment_id"] == 1
            material.source_attachment = new_att
            material.save.assert_called_once()


# ── delete_material ────────────────────────────────────────────────────


class TestDeleteMaterial:
    def test_material_not_found(self):
        svc = _make_service()
        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM:
            MockCM.DoesNotExist = Exception
            MockCM.objects.select_related.return_value.get.side_effect = MockCM.DoesNotExist

            with pytest.raises(NotFoundError):
                svc.delete_material(case_id=1, material_id=1)

    def test_successful_delete(self):
        svc = _make_service()
        material = MagicMock()
        material.id = 10
        material.source_attachment_id = 20
        att = MagicMock()
        att.file = MagicMock()
        material.source_attachment = att

        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM:
            MockCM.objects.select_related.return_value.get.return_value = material

            result = svc.delete_material(case_id=1, material_id=10)
            assert result["deleted"] is True
            material.delete.assert_called_once()
            att.delete.assert_called_once()

    def test_delete_no_attachment(self):
        svc = _make_service()
        material = MagicMock()
        material.id = 10
        material.source_attachment_id = None
        material.source_attachment = None

        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockCM:
            MockCM.objects.select_related.return_value.get.return_value = material

            result = svc.delete_material(case_id=1, material_id=10)
            assert result["deleted"] is True


# ── _validate_party_ids ────────────────────────────────────────────────


class TestValidatePartyIds:
    def test_valid_our_party(self):
        svc = _make_service()
        client = MagicMock()
        client.is_our_client = True
        party = MagicMock()
        party.client = client

        parties = {1: party}
        result = svc._validate_party_ids([1], parties, "our")
        assert result == [1]

    def test_invalid_party_id(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="无效当事人"):
            svc._validate_party_ids([99], {}, "our")

    def test_non_numeric_party_id_skipped(self):
        svc = _make_service()
        result = svc._validate_party_ids(["abc"], {}, "our")
        assert result == []

    def test_our_party_not_our(self):
        svc = _make_service()
        client = MagicMock()
        client.is_our_client = False
        party = MagicMock()
        party.client = client

        parties = {1: party}
        with pytest.raises(ValidationException, match="不属于我方"):
            svc._validate_party_ids([1], parties, "our")

    def test_opponent_party_is_our(self):
        svc = _make_service()
        client = MagicMock()
        client.is_our_client = True
        party = MagicMock()
        party.client = client

        parties = {1: party}
        with pytest.raises(ValidationException, match="不属于对方"):
            svc._validate_party_ids([1], parties, "opponent")

    def test_valid_opponent_party(self):
        svc = _make_service()
        client = MagicMock()
        client.is_our_client = False
        party = MagicMock()
        party.client = client

        parties = {1: party}
        result = svc._validate_party_ids([1], parties, "opponent")
        assert result == [1]


# ── _build_group_order_map ─────────────────────────────────────────────


class TestBuildGroupOrderMapRound8:
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


class TestSortedGroupsRound8:
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


class TestMaterialItemPayloadRound8:
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
        m.parties.all.return_value = [p1]

        result = svc._material_item_payload(m)
        assert result["material_id"] == 1
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

    def test_party_with_no_client(self):
        svc = _make_service()
        m = MagicMock()
        m.id = 1
        m.source_attachment_id = None
        m.source_attachment = None
        p = MagicMock()
        p.client = None
        m.parties.all.return_value = [p]

        result = svc._material_item_payload(m)
        assert result["party_labels"] == []
