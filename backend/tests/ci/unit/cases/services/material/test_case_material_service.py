"""Tests for cases.services.material.case_material_service."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from apps.cases.services.material.case_material_service import CaseMaterialService
from apps.core.exceptions import NotFoundError, ValidationException


def _make_service(**overrides: Any) -> CaseMaterialService:
    case_service = overrides.pop("case_service", MagicMock())
    query_service = overrides.pop("query_service", MagicMock())
    binding_workflow = overrides.pop("binding_workflow", MagicMock())
    return CaseMaterialService(
        case_service=case_service,
        query_service=query_service,
        binding_workflow=binding_workflow,
    )


class TestCaseMaterialServiceInit:
    def test_init_requires_case_service(self):
        with pytest.raises(RuntimeError, match="case_service"):
            CaseMaterialService(case_service=None)

    def test_init_success(self):
        svc = _make_service()
        assert svc._case_service is not None

    def test_query_service_lazy_load(self):
        svc = CaseMaterialService(case_service=MagicMock(), query_service=None, binding_workflow=None)
        # Lazy load: accessing query_service when _query_service is None triggers import
        qs = svc.query_service
        assert qs is not None

    def test_binding_workflow_lazy_load(self):
        svc = CaseMaterialService(case_service=MagicMock(), query_service=None, binding_workflow=None)
        bw = svc.binding_workflow
        assert bw is not None


class TestCaseMaterialServiceDelegateMethods:
    def test_list_bind_candidates(self):
        svc = _make_service()
        svc._query_service.list_bind_candidates.return_value = [{"id": 1}]
        result = svc.list_bind_candidates(case_id=1, user=None)
        assert result == [{"id": 1}]

    def test_bind_materials(self):
        svc = _make_service()
        svc._binding_workflow.bind_materials.return_value = [MagicMock()]
        result = svc.bind_materials(case_id=1, items=[{"type": "a"}])
        assert len(result) == 1

    def test_get_case_materials_view(self):
        svc = _make_service()
        svc._query_service.get_case_materials_view.return_value = {"groups": []}
        result = svc.get_case_materials_view(case_id=1)
        assert result == {"groups": []}

    def test_get_used_type_ids(self):
        svc = _make_service()
        svc._query_service.get_used_type_ids.return_value = {1, 2}
        result = svc.get_used_type_ids(case_id=1)
        assert result == {1, 2}

    def test_get_material_types_by_category(self):
        svc = _make_service()
        svc._query_service.get_material_types_by_category.return_value = [{"id": 1}]
        result = svc.get_material_types_by_category("party", 1, {1})
        assert result == [{"id": 1}]


class TestCaseMaterialServiceSaveGroupOrder:
    def test_save_group_order_invalid_category(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="材料大类不合法"):
            svc.save_group_order(case_id=1, category="invalid", ordered_type_ids=[1])

    def test_save_group_order_party_invalid_side(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="当事人方向不合法"):
            svc.save_group_order(case_id=1, category="party", ordered_type_ids=[1], side="wrong")

    def test_save_group_order_non_party_no_authority(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="必须选择主管机关"):
            svc.save_group_order(case_id=1, category="non_party", ordered_type_ids=[1])


class TestCaseMaterialServiceResolveType:
    @patch("apps.cases.services.material.case_material_service.CaseMaterialType")
    def test_resolve_type_by_id(self, MockType):
        svc = _make_service()
        mock_type = MagicMock()
        MockType.objects.get.return_value = mock_type
        result = svc._resolve_type("party", type_id=1, type_name="test", law_firm_id=None)
        assert result == mock_type


class TestCaseMaterialServiceValidatePartyIds:
    def test_validate_party_ids_invalid_id(self):
        svc = _make_service()
        parties = {}
        result = svc._validate_party_ids(["abc"], parties, "our")
        assert result == []

    def test_validate_party_ids_missing_party(self):
        svc = _make_service()
        with pytest.raises(ValidationException, match="包含无效当事人"):
            svc._validate_party_ids([1], {}, "our")

    def test_validate_party_ids_wrong_side(self):
        svc = _make_service()
        party = MagicMock()
        party.client.is_our_client = False
        parties = {1: party}
        with pytest.raises(ValidationException, match="当事人不属于我方"):
            svc._validate_party_ids([1], parties, "our")

    def test_validate_party_ids_opponent_wrong_side(self):
        svc = _make_service()
        party = MagicMock()
        party.client.is_our_client = True
        parties = {1: party}
        with pytest.raises(ValidationException, match="当事人不属于对方"):
            svc._validate_party_ids([1], parties, "opponent")

    def test_validate_party_ids_success(self):
        svc = _make_service()
        party = MagicMock()
        party.client.is_our_client = True
        parties = {1: party}
        result = svc._validate_party_ids([1], parties, "our")
        assert result == [1]


class TestCaseMaterialServiceBuildGroupOrderMap:
    def test_build_group_order_map(self):
        svc = _make_service()
        row1 = MagicMock()
        row1.category = "party"
        row1.side = "our"
        row1.supervising_authority_id = None
        row1.type_id = 1
        row2 = MagicMock()
        row2.category = "party"
        row2.side = "our"
        row2.supervising_authority_id = None
        row2.type_id = 2
        result = svc._build_group_order_map([row1, row2])
        assert ("party", "our", 0) in result
        assert result[("party", "our", 0)] == [1, 2]


class TestCaseMaterialServiceSortedGroups:
    def test_sorted_groups_with_order(self):
        svc = _make_service()
        groups = {1: {"type_name": "A"}, 2: {"type_name": "B"}}
        order_map = {("party", "our", 0): [2, 1]}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert result[0]["type_name"] == "B"
        assert result[1]["type_name"] == "A"

    def test_sorted_groups_no_order(self):
        svc = _make_service()
        groups = {1: {"type_name": "B"}, 2: {"type_name": "A"}}
        order_map = {}
        result = svc._sorted_groups("party", "our", None, groups, order_map)
        assert result[0]["type_name"] == "A"
        assert result[1]["type_name"] == "B"


class TestCaseMaterialServiceMaterialItemPayload:
    def test_material_item_payload_no_attachment(self):
        svc = _make_service()
        m = MagicMock()
        m.source_attachment = None
        m.parties.all.return_value = []
        result = svc._material_item_payload(m)
        assert result["file_name"] == ""
        assert result["file_url"] == ""

    def test_material_item_payload_with_attachment(self):
        svc = _make_service()
        m = MagicMock()
        m.source_attachment.original_filename = "test.pdf"
        m.source_attachment.file.url = "/media/test.pdf"
        m.source_attachment.uploaded_at = "2024-01-01"
        m.parties.all.return_value = []
        result = svc._material_item_payload(m)
        assert result["file_name"] == "test.pdf"


class TestCaseMaterialServiceRenameGroup:
    @patch("apps.cases.services.material.case_material_service.CaseMaterialType")
    @patch("apps.cases.services.material.case_material_service.CaseMaterial")
    @patch("apps.cases.services.material.case_material_service.transaction")
    def test_rename_group_same_name(self, mock_tx, MockMaterial, MockType):
        svc = _make_service()
        mock_type = MagicMock()
        mock_type.name = "old_name"
        MockType.objects.get.return_value = mock_type
        result = svc.rename_group(case_id=1, type_id=1, new_type_name="old_name")
        assert result["old_type_name"] == "old_name"

    @patch("apps.cases.services.material.case_material_service.CaseMaterialType")
    @patch("apps.cases.services.material.case_material_service.CaseMaterial")
    @patch("apps.cases.services.material.case_material_service.transaction")
    def test_rename_group_empty_name_raises(self, mock_tx, MockMaterial, MockType):
        svc = _make_service()
        with pytest.raises(ValidationException, match="类型名称不能为空"):
            svc.rename_group(case_id=1, type_id=1, new_type_name="  ")


class TestCaseMaterialServiceDeleteMaterial:
    @patch("apps.cases.services.material.case_material_service.CaseMaterialGroupOrder")
    def test_delete_all_materials_empty(self, MockGroupOrder):
        svc = _make_service()
        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockMat:
            MockMat.objects.select_related().filter.return_value = []
            result = svc.delete_all_materials(case_id=1, category="party")
            assert result["deleted_count"] == 0


class TestCaseMaterialServiceReplaceFile:
    def test_replace_same_attachment_raises(self):
        svc = _make_service()
        with patch("apps.cases.services.material.case_material_service.CaseMaterial") as MockMat:
            mock_mat = MagicMock()
            mock_mat.source_attachment_id = 5
            MockMat.objects.select_related().get.return_value = mock_mat
            with pytest.raises(ValidationException, match="新附件与当前附件相同"):
                svc.replace_material_file(case_id=1, material_id=1, new_attachment_id=5)
