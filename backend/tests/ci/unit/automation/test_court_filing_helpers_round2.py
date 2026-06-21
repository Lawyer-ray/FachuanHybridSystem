"""Additional coverage tests for court_filing_helpers uncovered branches."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
try:
    from plugins.court_automation import filing  # noqa: F401
except ImportError:
    pytest.skip("court_automation plugin not installed", allow_module_level=True)



class TestMatchSlotExecutionFallback:
    """Cover execution-specific fallback in _match_slot."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _match_slot
        return _match_slot

    def test_execution_apply_hits_returns_slot_0(self):
        """When filing_type=execution and signals contain execution keywords."""
        from plugins.court_automation.filing.helpers import _FILING_TYPE_EXECUTION

        material = MagicMock()
        material.type_name = "执行申请书"
        material.type = None
        material.source_attachment = None

        result = self._fn()(material=material, file_path=Path("/test/执行申请书.pdf"), filing_type=_FILING_TYPE_EXECUTION)
        assert result == "0"

    def test_execution_excluded_keywords_still_match_slot_rules(self):
        """When execution keywords are present alongside excluded keywords, slot rules may still match."""
        from plugins.court_automation.filing.helpers import _FILING_TYPE_EXECUTION

        material = MagicMock()
        material.type_name = "限制高消费 纳入失信"
        material.type = None
        material.source_attachment = None

        result = self._fn()(material=material, file_path=Path("/test/file.pdf"), filing_type=_FILING_TYPE_EXECUTION)
        # With only exclude keywords and no positive hits, should fall to default
        assert result == "4"

    def test_delivery_address_returns_slot_4(self):
        from plugins.court_automation.filing.helpers import _FILING_TYPE_CIVIL

        material = MagicMock()
        material.type_name = "送达地址确认"
        material.type = None
        material.source_attachment = None

        result = self._fn()(material=material, file_path=Path("/test/送达地址确认.pdf"), filing_type=_FILING_TYPE_CIVIL)
        assert result == "4"

    def test_preservation_returns_slot_5(self):
        from plugins.court_automation.filing.helpers import _FILING_TYPE_CIVIL

        material = MagicMock()
        material.type_name = "保全申请"
        material.type = None
        material.source_attachment = None

        result = self._fn()(material=material, file_path=Path("/test/保全申请.pdf"), filing_type=_FILING_TYPE_CIVIL)
        assert result == "5"


class TestBuildMaterialSlotSignals:
    """Cover additional _build_material_slot_signals branches."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_material_slot_signals
        return _build_material_slot_signals

    def test_with_material_type_name(self):
        material = MagicMock()
        material.type_name = "起诉状"
        material_type = MagicMock()
        material_type.name = "民事起诉状"
        material.type = material_type
        attachment = MagicMock()
        attachment.file.name = "/test/起诉状.pdf"
        attachment.log = None
        material.source_attachment = attachment

        primary, secondary = self._fn()(material=material, file_path=Path("/test/起诉状.pdf"))
        assert any("起诉状" in s for s in primary)

    def test_with_attachment_log(self):
        material = MagicMock()
        material.type_name = "证据"
        material.type = None
        attachment = MagicMock()
        attachment.file.name = "/test/file.pdf"
        log = MagicMock()
        log.content = "logcontent"
        attachment.log = log
        material.source_attachment = attachment

        primary, secondary = self._fn()(material=material, file_path=Path("/test/file.pdf"))
        assert any("logcontent" in s for s in secondary)

    def test_dedup_signals(self):
        material = MagicMock()
        material.type_name = "起诉状"
        material.type = None
        material.source_attachment = None

        # Same signal should not appear twice
        primary, secondary = self._fn()(
            material=material,
            file_path=Path("/test/起诉状/起诉状.pdf"),
        )
        # type_name only appears once in primary
        assert primary.count(primary[0]) == 1 if primary else True


class TestScoreSlotDeduplicated:
    """Cover _score_slot_deduplicated with no signals."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _score_slot_deduplicated
        return _score_slot_deduplicated

    def test_no_signals_returns_zero(self):
        result = self._fn()(
            primary_signals=[],
            secondary_signals=[],
            strong=("a",),
            weak=(),
            exclude=(),
        )
        assert result == 0


class TestInferFilingTypeMaterialKeywords:
    """Cover material keyword matching in _infer_filing_type."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _infer_filing_type
        return _infer_filing_type

    def test_material_has_execution_keyword(self):
        from plugins.court_automation.filing.helpers import _FILING_TYPE_EXECUTION

        case = MagicMock()
        case.name = "test"
        case.cause_of_action = ""

        mock_materials = MagicMock()
        mock_materials.values_list.return_value = ["执行申请书"]

        with patch("apps.cases.models.CaseMaterial") as mock_cm:
            mock_cm.objects.filter.return_value.values_list.return_value = ["执行申请书"]
            result = self._fn()(case=case, parties=[])
        assert result == _FILING_TYPE_EXECUTION


class TestBuildExecutionRequestTextBranches:
    """Cover branches in _build_execution_request_text."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_execution_request_text
        return _build_execution_request_text

    def test_generated_text_with_bell_char(self):
        case = MagicMock()
        case.id = 1

        with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService") as mock_svc:
            from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys
            mock_instance = MagicMock()
            mock_instance.generate.return_value = {
                LitigationPlaceholderKeys.ENFORCEMENT_EXECUTION_REQUEST: "line1\aline2\r\nline3\rline4"
            }
            mock_svc.return_value = mock_instance
            result = self._fn()(case=case)
        assert "\n" in result
        assert "\a" not in result

    def test_type_error_in_generation(self):
        case = MagicMock()
        case.id = 1
        case.case_numbers = MagicMock()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = None

        with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService", side_effect=TypeError("bad type")):
            result = self._fn()(case=case)
        assert "一、" in result

    def test_fallback_with_case_number(self):
        case = MagicMock()
        case.id = 1
        case.case_numbers = MagicMock()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2025)粤01民初1号"

        with patch("apps.documents.services.placeholders.litigation.execution_request_service.ExecutionRequestService") as mock_svc:
            mock_instance = MagicMock()
            mock_instance.generate.return_value = {}
            mock_svc.return_value = mock_instance
            result = self._fn()(case=case)
        assert "(2025)粤01民初1号" in result


class TestBuildAgentPayloadsEdgeCases:
    """Cover edge cases in _build_agent_payloads."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_agent_payloads
        return _build_agent_payloads

    def test_lawyer_with_no_name_skipped(self):
        case = MagicMock()
        assignment = MagicMock()
        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = ""
        lawyer.username = ""
        lawyer.phone = ""
        lawyer.id_card = ""
        lawyer.license_no = ""
        lawyer.law_firm = None
        assignment.lawyer = lawyer
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        parties = []
        result = self._fn()(case=case, requester_id=None, parties=parties)
        assert result == []

    def test_requester_not_in_seen_ids(self):
        case = MagicMock()
        case.assignments.select_related.return_value.order_by.return_value = []

        party_client = MagicMock()
        party_client.phone = "13800138000"
        party = MagicMock()
        party.client = party_client
        parties = [party]

        with patch("apps.organization.models.Lawyer") as mock_lawyer_model:
            requester = MagicMock()
            requester.id = 999
            requester.real_name = "请求者律师"
            requester.username = "req_user"
            requester.phone = "13900139000"
            requester.id_card = "440100199901010001"
            requester.license_no = "A20240001"
            requester.law_firm = MagicMock(name="测试律所", address="测试地址")
            mock_lawyer_model.objects.select_related.return_value.filter.return_value.first.return_value = requester

            result = self._fn()(case=case, requester_id=999, parties=parties)
        assert len(result) == 1
        assert result[0]["name"] == "请求者律师"

    def test_lawyer_fallback_phone_from_parties(self):
        case = MagicMock()
        assignment = MagicMock()
        lawyer = MagicMock()
        lawyer.id = 1
        lawyer.real_name = "律师A"
        lawyer.username = "user_a"
        lawyer.phone = ""
        lawyer.id_card = ""
        lawyer.license_no = ""
        law_firm = MagicMock()
        law_firm.name = "律所A"
        law_firm.address = "地址A"
        lawyer.law_firm = law_firm
        assignment.lawyer = lawyer
        case.assignments.select_related.return_value.order_by.return_value = [assignment]

        party_client = MagicMock()
        party_client.phone = "13800138000"
        party = MagicMock()
        party.client = party_client
        parties = [party]

        result = self._fn()(case=case, requester_id=None, parties=parties)
        assert len(result) == 1
        assert result[0]["phone"] == "13800138000"


class TestBuildMaterialsMapNoMaterials:
    """Cover _build_materials_map fallback to all materials."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _build_materials_map
        return _build_materials_map

    def test_no_party_materials_fallback(self):
        case = MagicMock()

        with patch("apps.cases.models.CaseMaterial") as mock_cm, \
             patch("apps.cases.models.CaseMaterialCategory") as mock_cat, \
             patch("apps.cases.models.CaseMaterialSide") as mock_side:
            # First query (party materials) returns empty - chain: filter -> filter -> select_related -> order_by
            party_ordered = MagicMock()
            party_ordered.exists.return_value = False
            party_ordered.__iter__ = MagicMock(return_value=iter([]))

            party_select = MagicMock()
            party_select.order_by.return_value = party_ordered

            party_filter2 = MagicMock()
            party_filter2.select_related.return_value = party_select

            party_filter1 = MagicMock()
            party_filter1.filter.return_value = party_filter2

            # Second query (all materials) returns something
            material = MagicMock()
            material.source_attachment_id = 1
            attachment = MagicMock()
            attachment.file.path = "/test/file.pdf"
            attachment.original_filename = "file.pdf"
            material.source_attachment = attachment

            all_ordered = MagicMock()
            all_ordered.__iter__ = MagicMock(return_value=iter([material]))

            all_select = MagicMock()
            all_select.order_by.return_value = all_ordered

            all_filter = MagicMock()
            all_filter.select_related.return_value = all_select

            mock_cm.objects.filter.side_effect = [party_filter1, all_filter]

            with patch("plugins.court_automation.filing.helpers._match_slot", return_value="5"), \
                 patch("pathlib.Path.exists", return_value=True):
                result = self._fn()(case=case, filing_type="civil")
            assert isinstance(result, dict)

    def _build_qs_chain(self, materials):
        """Helper to build a queryset chain for _build_materials_map."""
        ordered = MagicMock()
        ordered.exists.return_value = len(materials) > 0
        ordered.__iter__ = MagicMock(return_value=iter(materials))

        select = MagicMock()
        select.order_by.return_value = ordered

        filter2 = MagicMock()
        filter2.select_related.return_value = select

        filter1 = MagicMock()
        filter1.filter.return_value = filter2
        return filter1

    def test_material_without_source_attachment_skipped(self):
        case = MagicMock()

        with patch("apps.cases.models.CaseMaterial") as mock_cm, \
             patch("apps.cases.models.CaseMaterialCategory") as mock_cat, \
             patch("apps.cases.models.CaseMaterialSide") as mock_side:
            material = MagicMock()
            material.source_attachment_id = None

            qs = self._build_qs_chain([material])
            mock_cm.objects.filter.return_value = qs

            result = self._fn()(case=case, filing_type="civil")
            assert result == {}

    def test_material_file_not_pdf_skipped(self):
        case = MagicMock()

        with patch("apps.cases.models.CaseMaterial") as mock_cm, \
             patch("apps.cases.models.CaseMaterialCategory") as mock_cat, \
             patch("apps.cases.models.CaseMaterialSide") as mock_side:
            material = MagicMock()
            material.source_attachment_id = 1
            attachment = MagicMock()
            attachment.file.path = "/test/file.docx"
            attachment.original_filename = "file.docx"
            material.source_attachment = attachment

            qs = self._build_qs_chain([material])
            mock_cm.objects.filter.return_value = qs

            with patch("pathlib.Path.exists", return_value=True):
                result = self._fn()(case=case, filing_type="civil")
            assert result == {}

    def test_material_file_path_exception_skipped(self):
        case = MagicMock()

        with patch("apps.cases.models.CaseMaterial") as mock_cm, \
             patch("apps.cases.models.CaseMaterialCategory") as mock_cat, \
             patch("apps.cases.models.CaseMaterialSide") as mock_side:
            material = MagicMock()
            material.source_attachment_id = 1
            attachment = MagicMock()
            # Make attachment.file.path raise
            attachment.configure_mock(**{})
            file_mock = MagicMock()
            type(file_mock).path = property(lambda self: (_ for _ in ()).throw(ValueError("no path")))
            attachment.file = file_mock
            material.source_attachment = attachment

            qs = self._build_qs_chain([material])
            mock_cm.objects.filter.return_value = qs

            result = self._fn()(case=case, filing_type="civil")
            assert result == {}

    def test_dedup_prevents_duplicate(self):
        case = MagicMock()

        with patch("apps.cases.models.CaseMaterial") as mock_cm, \
             patch("apps.cases.models.CaseMaterialCategory") as mock_cat, \
             patch("apps.cases.models.CaseMaterialSide") as mock_side:
            # Two materials pointing to same file
            materials = []
            for _ in range(2):
                material = MagicMock()
                material.source_attachment_id = 1
                attachment = MagicMock()
                attachment.file.path = "/test/same.pdf"
                attachment.original_filename = "same.pdf"
                material.source_attachment = attachment
                materials.append(material)

            qs = self._build_qs_chain(materials)
            mock_cm.objects.filter.return_value = qs

            with patch("plugins.court_automation.filing.helpers._match_slot", return_value="5"), \
                 patch("pathlib.Path.exists", return_value=True):
                result = self._fn()(case=case, filing_type="civil")
            # Should only have 1 entry despite 2 materials
            assert len(result.get("5", [])) == 1


class TestScoreSlotForSignalEdgeCases:
    """Cover additional _score_slot_for_signal branches."""

    def _fn(self):
        from plugins.court_automation.filing.helpers import _score_slot_for_signal
        return _score_slot_for_signal

    def test_exclude_keywords_reduce_score(self):
        result = self._fn()(
            signal="营业执照 委托代理",
            strong=(),
            weak=(),
            exclude=("委托代理",),
        )
        assert result < 0

    def test_combined_scoring(self):
        result = self._fn()(
            signal="授权委托书 代理人",
            strong=("授权委托书",),
            weak=("代理人",),
            exclude=("送达地址",),
        )
        assert result > 0
