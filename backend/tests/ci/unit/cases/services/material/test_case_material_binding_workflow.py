"""Tests for cases.services.material.case_material_binding_workflow.

Covers: __init__, case_service property, _validate_party_ids, _resolve_type_cached,
_bind_materials validation paths.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestCaseMaterialBindingWorkflowInit:
    def test_default_init(self):
        from apps.cases.services.material.case_material_binding_workflow import (
            CaseMaterialBindingWorkflow,
        )
        wf = CaseMaterialBindingWorkflow()
        assert wf._case_service is None

    def test_injected_service(self):
        from apps.cases.services.material.case_material_binding_workflow import (
            CaseMaterialBindingWorkflow,
        )
        mock_svc = MagicMock()
        wf = CaseMaterialBindingWorkflow(case_service=mock_svc)
        assert wf.case_service is mock_svc

    def test_case_service_not_injected_raises(self):
        from apps.cases.services.material.case_material_binding_workflow import (
            CaseMaterialBindingWorkflow,
        )
        wf = CaseMaterialBindingWorkflow()
        with pytest.raises(RuntimeError, match="未注入"):
            _ = wf.case_service


class TestValidatePartyIds:
    def _make_workflow(self):
        from apps.cases.services.material.case_material_binding_workflow import (
            CaseMaterialBindingWorkflow,
        )
        return CaseMaterialBindingWorkflow(case_service=MagicMock())

    def test_valid_ids(self):
        wf = self._make_workflow()
        party = SimpleNamespace(client=SimpleNamespace(is_our_client=True))
        parties = {1: party, 2: party}
        result = wf._validate_party_ids([1, 2], parties, "our")
        assert result == [1, 2]

    def test_invalid_string_id_skipped(self):
        wf = self._make_workflow()
        result = wf._validate_party_ids(["not_int"], {}, "our")
        assert result == []

    def test_missing_party_raises(self):
        wf = self._make_workflow()
        with pytest.raises(Exception, match="无效当事人"):
            wf._validate_party_ids([999], {}, "our")

    def test_our_side_non_our_party_raises(self):
        wf = self._make_workflow()
        party = SimpleNamespace(client=SimpleNamespace(is_our_client=False))
        parties = {1: party}
        with pytest.raises(Exception, match="不属于我方"):
            wf._validate_party_ids([1], parties, "our")

    def test_opponent_side_our_party_raises(self):
        wf = self._make_workflow()
        party = SimpleNamespace(client=SimpleNamespace(is_our_client=True))
        parties = {1: party}
        with pytest.raises(Exception, match="不属于对方"):
            wf._validate_party_ids([1], parties, "opponent")

    def test_none_client_treated_as_not_our(self):
        wf = self._make_workflow()
        party = SimpleNamespace(client=None)
        parties = {1: party}
        # is_our_client on None would use getattr(getattr(...), ..., False) = False
        # so for OUR side, this should raise
        with pytest.raises(Exception):
            wf._validate_party_ids([1], parties, "our")


class TestResolveTypeCached:
    def _make_workflow(self):
        from apps.cases.services.material.case_material_binding_workflow import (
            CaseMaterialBindingWorkflow,
        )
        return CaseMaterialBindingWorkflow(case_service=MagicMock())

    def test_cache_hit(self):
        wf = self._make_workflow()
        mock_type = SimpleNamespace(id=1)
        cache = {"id:1": mock_type}
        result = wf._resolve_type_cached(
            cache=cache, category="party", type_id=1, type_name="test", law_firm_id=None
        )
        assert result is mock_type

    def test_cache_miss(self):
        wf = self._make_workflow()
        cache = {}
        with patch.object(wf, "_resolve_type", return_value="resolved_type") as mock_resolve:
            result = wf._resolve_type_cached(
                cache=cache, category="party", type_id=1, type_name="test", law_firm_id=None
            )
            assert result == "resolved_type"
            mock_resolve.assert_called_once()


class TestBindMaterialsValidation:
    """Test the validation logic inside bind_materials (skips DB calls)."""

    def _make_workflow(self):
        from apps.cases.services.material.case_material_binding_workflow import (
            CaseMaterialBindingWorkflow,
        )
        case_service = MagicMock()
        case_service.get_case.return_value = MagicMock()
        return CaseMaterialBindingWorkflow(case_service=case_service)

    def _run_bind_with_validation_error(self, wf, items):
        """Run bind_materials with DB mocks so validation errors are hit."""
        with patch("apps.cases.services.material.case_material_binding_workflow.CaseLogAttachment") as MockAtt, \
             patch("apps.cases.services.material.case_material_binding_workflow.CaseParty") as MockParty, \
             patch("apps.cases.services.material.case_material_binding_workflow.SupervisingAuthority") as MockAuth, \
             patch("apps.cases.services.material.case_material_binding_workflow.transaction") as mock_txn:
            mock_txn.atomic.return_value.__enter__ = MagicMock()
            mock_txn.atomic.return_value.__exit__ = MagicMock(return_value=False)
            # Return mock attachments matching the ids in items
            mock_attachments = []
            for item in items:
                att = MagicMock()
                att.id = int(item.get("attachment_id", 0))
                mock_attachments.append(att)
            MockAtt.objects.filter.return_value.select_related.return_value = mock_attachments
            MockParty.objects.filter.return_value.select_related.return_value.all.return_value = []
            MockAuth.objects.filter.return_value.all.return_value = []
            wf.bind_materials(
                case_id=1, items=items, user=MagicMock()
            )

    def test_invalid_category_raises(self):
        wf = self._make_workflow()
        with pytest.raises(Exception, match="材料大类不合法"):
            self._run_bind_with_validation_error(wf, [{
                "attachment_id": 1,
                "category": "invalid",
                "type_name": "test",
            }])

    def test_empty_type_name_raises(self):
        wf = self._make_workflow()
        with pytest.raises(Exception, match="类型名称不能为空"):
            self._run_bind_with_validation_error(wf, [{
                "attachment_id": 1,
                "category": "party",
                "type_name": "",
            }])

    def test_party_invalid_side_raises(self):
        wf = self._make_workflow()
        with pytest.raises(Exception, match="当事人方向不合法"):
            self._run_bind_with_validation_error(wf, [{
                "attachment_id": 1,
                "category": "party",
                "type_name": "test",
                "side": "invalid_side",
            }])

    def test_non_party_no_authority_raises(self):
        wf = self._make_workflow()
        with pytest.raises(Exception, match="必须选择主管机关"):
            self._run_bind_with_validation_error(wf, [{
                "attachment_id": 1,
                "category": "non_party",
                "type_name": "test",
                "supervising_authority_id": None,
            }])
