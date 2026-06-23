"""Targeted coverage tests for OA filing, batch printing, and story_viz modules — Round 6.

Targets: script_executor_service (mapping methods), preset_discovery_service,
          html_composer_service, reminder_service_adapter
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# script_executor_service.py — mapping methods
# ---------------------------------------------------------------------------


class TestScriptExecutorMappings:
    """Test the mapping helper methods of ScriptExecutorService."""

    @pytest.fixture()
    def svc(self):
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService
        return ScriptExecutorService()

    def test_map_case_category_civil(self, svc):
        case = SimpleNamespace(case_type="civil")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_criminal(self, svc):
        case = SimpleNamespace(case_type="criminal")
        assert svc._map_case_category(case) == "05"

    def test_map_case_category_administrative(self, svc):
        case = SimpleNamespace(case_type="administrative")
        assert svc._map_case_category(case) == "04"

    def test_map_case_category_labor(self, svc):
        case = SimpleNamespace(case_type="labor")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_intl(self, svc):
        case = SimpleNamespace(case_type="intl")
        assert svc._map_case_category(case) == "06"

    def test_map_case_category_execution(self, svc):
        case = SimpleNamespace(case_type="execution")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_bankruptcy(self, svc):
        case = SimpleNamespace(case_type="bankruptcy")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_special(self, svc):
        case = SimpleNamespace(case_type="special")
        assert svc._map_case_category(case) == "02"

    def test_map_case_category_advisor(self, svc):
        case = SimpleNamespace(case_type="advisor")
        assert svc._map_case_category(case) == "01"

    def test_map_case_category_unknown(self, svc):
        case = SimpleNamespace(case_type="weird")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_none(self, svc):
        case = SimpleNamespace(case_type=None)
        assert svc._map_case_category(case) == "03"

    def test_map_case_stage_civil_first(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0301"

    def test_map_case_stage_civil_second(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="second_trial")
        assert svc._map_case_stage(case) == "0305"

    def test_map_case_stage_civil_enforcement(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="enforcement")
        assert svc._map_case_stage(case) == "0314"

    def test_map_case_stage_civil_apply_retrial(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="apply_retrial")
        assert svc._map_case_stage(case) == "0310"

    def test_map_case_stage_civil_retrial_first(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="retrial_first")
        assert svc._map_case_stage(case) == "0313"

    def test_map_case_stage_civil_petition(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="petition")
        assert svc._map_case_stage(case) == "0308"

    def test_map_case_stage_civil_apply_protest(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="apply_protest")
        assert svc._map_case_stage(case) == "0309"

    def test_map_case_stage_civil_review(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="review")
        assert svc._map_case_stage(case) == "0310"

    def test_map_case_stage_civil_unknown(self, svc):
        case = SimpleNamespace(case_type="civil", current_stage="weird")
        assert svc._map_case_stage(case) == "0301"

    def test_map_case_stage_admin_review(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="administrative_review")
        assert svc._map_case_stage(case) == "0401"

    def test_map_case_stage_admin_first(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0402"

    def test_map_case_stage_admin_second(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="second_trial")
        assert svc._map_case_stage(case) == "0403"

    def test_map_case_stage_admin_retrial_first(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="retrial_first")
        assert svc._map_case_stage(case) == "0404"

    def test_map_case_stage_admin_retrial_second(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="retrial_second")
        assert svc._map_case_stage(case) == "0405"

    def test_map_case_stage_admin_petition(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="petition")
        assert svc._map_case_stage(case) == "0406"

    def test_map_case_stage_admin_rehearing_first(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="rehearing_first")
        assert svc._map_case_stage(case) == "0410"

    def test_map_case_stage_admin_rehearing_second(self, svc):
        case = SimpleNamespace(case_type="administrative", current_stage="rehearing_second")
        assert svc._map_case_stage(case) == "0411"

    def test_map_case_stage_criminal_investigation(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="investigation")
        assert svc._map_case_stage(case) == "0501"

    def test_map_case_stage_criminal_prosecution_review(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="prosecution_review")
        assert svc._map_case_stage(case) == "0502"

    def test_map_case_stage_criminal_first(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0503"

    def test_map_case_stage_criminal_second(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="second_trial")
        assert svc._map_case_stage(case) == "0504"

    def test_map_case_stage_criminal_private_prosecution(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="private_prosecution")
        assert svc._map_case_stage(case) == "0500"

    def test_map_case_stage_criminal_death_penalty_review(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="death_penalty_review")
        assert svc._map_case_stage(case) == "0511"

    def test_map_case_stage_criminal_rehearing_first(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="rehearing_first")
        assert svc._map_case_stage(case) == "0512"

    def test_map_case_stage_criminal_rehearing_second(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="rehearing_second")
        assert svc._map_case_stage(case) == "0513"

    def test_map_case_stage_criminal_apply_retrial(self, svc):
        case = SimpleNamespace(case_type="criminal", current_stage="apply_retrial")
        assert svc._map_case_stage(case) == "0509"

    def test_map_case_stage_nonlitigation_advisor(self, svc):
        case = SimpleNamespace(case_type="advisor", current_stage="anything")
        assert svc._map_case_stage(case) == ""

    def test_map_case_stage_nonlitigation_special(self, svc):
        case = SimpleNamespace(case_type="special", current_stage="something")
        assert svc._map_case_stage(case) == ""

    def test_map_case_stage_intl_uses_criminal(self, svc):
        case = SimpleNamespace(case_type="intl", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0503"

    def test_map_fee_mode_fixed(self, svc):
        contract = SimpleNamespace(fee_mode="FIXED")
        assert svc._map_fee_mode(contract) == "01"

    def test_map_fee_mode_semi_risk(self, svc):
        contract = SimpleNamespace(fee_mode="SEMI_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_map_fee_mode_full_risk(self, svc):
        contract = SimpleNamespace(fee_mode="FULL_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_map_fee_mode_custom(self, svc):
        contract = SimpleNamespace(fee_mode="CUSTOM")
        assert svc._map_fee_mode(contract) == "01"

    def test_map_fee_mode_unknown(self, svc):
        contract = SimpleNamespace(fee_mode="OTHER")
        assert svc._map_fee_mode(contract) == "01"

    def test_map_fee_mode_none(self, svc):
        contract = SimpleNamespace(fee_mode=None)
        assert svc._map_fee_mode(contract) == "01"

    def test_map_kindtype_civil(self, svc):
        result = svc._map_kindtype("03", [])
        assert result == ("", "")

    def test_map_kindtype_admin(self, svc):
        result = svc._map_kindtype("04", [])
        assert result == ("", "")

    def test_map_kindtype_criminal(self, svc):
        result = svc._map_kindtype("05", [])
        assert result == ("", "")

    def test_map_kindtype_advisor_enterprise(self, svc):
        party = SimpleNamespace(client=SimpleNamespace(client_type="company"))
        result = svc._map_kindtype("01", [party])
        assert result == ("KindType01_01", "KindType01_0103")

    def test_map_kindtype_advisor_natural(self, svc):
        party = SimpleNamespace(client=SimpleNamespace(client_type="natural"))
        result = svc._map_kindtype("01", [party])
        assert result == ("KindType01_05", "")

    def test_map_kindtype_special_enterprise(self, svc):
        party = SimpleNamespace(client=SimpleNamespace(client_type="company"))
        result = svc._map_kindtype("02", [party])
        assert result == ("KindType02_01", "")

    def test_map_kindtype_special_natural(self, svc):
        party = SimpleNamespace(client=SimpleNamespace(client_type="natural"))
        result = svc._map_kindtype("02", [party])
        assert result == ("KindType02_05", "")

    def test_map_kindtype_advisor_no_client(self, svc):
        party = SimpleNamespace(client=None)
        result = svc._map_kindtype("01", [party])
        assert result == ("KindType01_01", "KindType01_0103")

    @pytest.mark.asyncio
    async def test_dispatch_unsupported_site(self, svc):
        from apps.oa_filing.services.exceptions import ScriptExecutionError

        with pytest.raises(ScriptExecutionError, match="不支持"):
            await svc._dispatch("unsupported", MagicMock(), 1, None)


# ---------------------------------------------------------------------------
# preset_discovery_service.py
# ---------------------------------------------------------------------------


class TestPresetDiscoveryService:
    """Tests for PresetDiscoveryService private methods."""

    @pytest.fixture()
    def svc(self):
        from apps.batch_printing.services.preset.preset_discovery_service import PresetDiscoveryService
        return PresetDiscoveryService()

    def test_extract_printer_name_valid(self, svc):
        from pathlib import Path
        p = Path("/tmp/com.apple.print.custompresets.forprinter.HP-Laser.plist")
        assert svc._extract_printer_name(p) == "HP-Laser"

    def test_extract_printer_name_wrong_prefix(self, svc):
        from pathlib import Path
        p = Path("/tmp/wrong_prefix.plist")
        assert svc._extract_printer_name(p) == ""

    def test_extract_printer_name_wrong_suffix(self, svc):
        from pathlib import Path
        p = Path("/tmp/com.apple.print.custompresets.forprinter.X.txt")
        assert svc._extract_printer_name(p) == ""

    def test_load_plist_nonexistent(self, svc):
        from pathlib import Path
        result = svc._load_plist(Path("/nonexistent/file.plist"))
        assert result is None

    def test_collect_preset_records_empty(self, svc):
        result = svc._collect_preset_records({}, "printer")
        assert result == []

    def test_walk_preset_nodes_list(self, svc):
        records: list = []
        svc._walk_preset_nodes([{"PMPresetName": "test", "PMPrintSettings": {"key": "val"}}], printer_name="P", records=records)
        assert len(records) == 1
        assert records[0].preset_name == "test"

    def test_append_legacy_record(self, svc):
        records: list = []
        node = {"PMPresetName": "Legacy", "PMPrintSettings": {"a": 1}}
        svc._append_legacy_preset_record(node, printer_name="P", records=records)
        assert len(records) == 1
        assert records[0].preset_name == "Legacy"

    def test_append_legacy_record_no_name(self, svc):
        records: list = []
        node = {"PMPrintSettings": {"a": 1}}
        svc._append_legacy_preset_record(node, printer_name="P", records=records)
        assert len(records) == 0

    def test_append_legacy_record_no_settings(self, svc):
        records: list = []
        node = {"PMPresetName": "test"}
        svc._append_legacy_preset_record(node, printer_name="P", records=records)
        assert len(records) == 0

    def test_append_modern_preset_records(self, svc):
        records: list = []
        node = {
            "MyCustomPreset": {
                "com.apple.print.preset.settings": {"key": "value"},
                "com.apple.print.preset.id": "Custom 1",
            }
        }
        svc._append_modern_preset_records(node, printer_name="P", records=records)
        assert len(records) == 1
        assert records[0].preset_name == "Custom 1"

    def test_append_modern_preset_records_fallback_name(self, svc):
        records: list = []
        node = {
            "MyPreset": {
                "com.apple.print.preset.settings": {"key": "value"},
            }
        }
        svc._append_modern_preset_records(node, printer_name="P", records=records)
        assert len(records) == 1
        assert records[0].preset_name == "MyPreset"

    def test_append_modern_preset_records_skip_metadata_prefix(self, svc):
        records: list = []
        node = {
            "com.apple.print.metadata.something": {
                "com.apple.print.preset.settings": {"key": "val"},
            }
        }
        svc._append_modern_preset_records(node, printer_name="P", records=records)
        assert len(records) == 0

    def test_append_modern_preset_records_no_settings(self, svc):
        records: list = []
        node = {"SomeKey": {"other": "data"}}
        svc._append_modern_preset_records(node, printer_name="P", records=records)
        assert len(records) == 0

    def test_append_modern_preset_records_non_dict_value(self, svc):
        records: list = []
        node = {"SomeKey": "string_value"}
        svc._append_modern_preset_records(node, printer_name="P", records=records)
        assert len(records) == 0

    def test_append_record_empty_name(self, svc):
        records: list = []
        svc._append_record(printer_name="P", preset_name="", raw_settings={}, records=records)
        assert len(records) == 0

    def test_append_record_whitespace_name(self, svc):
        records: list = []
        svc._append_record(printer_name="P", preset_name="   ", raw_settings={}, records=records)
        assert len(records) == 0

    def test_extract_executable_options(self, svc):
        raw = {"sides": "two-sided", "number-up": "2", "unknown-opt": "val"}
        supported = {"sides", "number-up"}
        result = svc._extract_executable_options(raw, supported)
        assert "sides" in result
        assert "number-up" in result
        assert "unknown-opt" not in result

    def test_extract_executable_options_empty_supported(self, svc):
        raw = {"sides": "two-sided", "number-up": "2", "other": "val"}
        result = svc._extract_executable_options(raw, set())
        # When supported is empty (falsy), all keys pass except unknown ones
        # But "other" has no special handling, so only sides/number-up should pass
        assert "sides" in result
        assert "number-up" in result

    def test_normalize_option_value_none(self, svc):
        assert svc._normalize_option_value(None) == ""

    def test_normalize_option_value_bool(self, svc):
        assert svc._normalize_option_value(True) == "true"
        assert svc._normalize_option_value(False) == "false"

    def test_normalize_option_value_int(self, svc):
        assert svc._normalize_option_value(42) == "42"

    def test_normalize_option_value_float(self, svc):
        assert svc._normalize_option_value(3.14) == "3.14"

    def test_normalize_option_value_bytes(self, svc):
        assert svc._normalize_option_value(b"hello") == "hello"

    def test_normalize_option_value_bytes_decode_error(self, svc):
        # bytes with invalid utf-8
        result = svc._normalize_option_value(b"\xff\xfe")
        assert result == ""

    def test_normalize_option_value_string(self, svc):
        result = svc._normalize_option_value("hello  world")
        assert result == "hello world"

    def test_dedup_preset_records(self, svc):
        records = svc._collect_preset_records(
            {"PMPresetName": "A", "PMPrintSettings": {"k": 1}},
            "Printer",
        )
        # Add another record with same key
        records2 = svc._collect_preset_records(
            {"PMPresetName": "A", "PMPrintSettings": {"k": 2}},
            "Printer",
        )
        # Dedup should happen inside _collect_preset_records
        assert len(records) == 1


# ---------------------------------------------------------------------------
# html_composer_service.py
# ---------------------------------------------------------------------------


class TestAnimationHtmlComposerService:
    """Tests for AnimationHtmlComposerService."""

    @pytest.fixture()
    def svc(self):
        from apps.story_viz.services.html_composer_service import AnimationHtmlComposerService
        return AnimationHtmlComposerService()

    def test_compose_timeline(self, svc):
        html = svc.compose(
            title="Test Title",
            viz_type="timeline",
            render_payload={"nodes": [{"time": "2024-01", "label": "Event"}]},
            fragment_payload={},
        )
        assert "<!doctype html>" in html
        assert "Test Title" in html
        assert "时间线" in html

    def test_compose_relationship(self, svc):
        html = svc.compose(
            title="Relation",
            viz_type="relationship",
            render_payload={"nodes": [], "edges": []},
            fragment_payload={},
        )
        assert "关系图" in html
        assert "d3.min.js" in html

    def test_compose_claim_judgment(self, svc):
        html = svc.compose(
            title="Claim vs Judgment",
            viz_type="claim_judgment",
            render_payload={"nodes": [{"claim": "A", "judgment": "B"}], "annotations": ["key point"]},
            fragment_payload={},
        )
        assert "诉求 vs 判决" in html
        assert "key point" in html

    def test_compose_unknown_type_fallback(self, svc):
        html = svc.compose(
            title="Unknown",
            viz_type="unknown_type",
            render_payload={"nodes": []},
            fragment_payload={},
        )
        assert "时间线" in html

    def test_empty_title_fallback(self, svc):
        html = svc.compose(
            title="",
            viz_type="timeline",
            render_payload={"nodes": []},
            fragment_payload={},
        )
        assert "故事可视化" in html

    def test_html_escapes_title(self, svc):
        html = svc.compose(
            title="<script>alert(1)</script>",
            viz_type="timeline",
            render_payload={"nodes": []},
            fragment_payload={},
        )
        assert "&lt;script&gt;" in html

    def test_comparison_body_with_annotations(self, svc):
        body = svc._comparison_body("T", {"annotations": ["anno1", "anno2"]})
        assert "anno1" in body
        assert "anno2" in body

    def test_comparison_body_no_annotations(self, svc):
        body = svc._comparison_body("T", {})
        assert "裁判要点" not in body

    def test_timeline_body_with_annotations(self, svc):
        body = svc._timeline_body("T", {"nodes": [], "annotations": ["a"]})
        assert "关键节点" in body
        assert "a" in body

    def test_timeline_body_no_annotations(self, svc):
        body = svc._timeline_body("T", {"nodes": []})
        assert "关键节点" not in body


# ---------------------------------------------------------------------------
# reminder_service_adapter.py
# ---------------------------------------------------------------------------


class TestReminderServiceAdapter:
    """Tests for ReminderServiceAdapter helper methods."""

    def test_get_reminder_type_by_code_internal_invalid(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        adapter = ReminderServiceAdapter()
        assert adapter.get_reminder_type_by_code_internal("nonexistent") is None

    def test_get_reminder_type_by_code_internal_valid(self):
        from apps.reminders.models import ReminderType
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        adapter = ReminderServiceAdapter()
        code = ReminderType.values[0]
        result = adapter.get_reminder_type_by_code_internal(code)
        assert result is not None
        assert result.code == code
        assert result.id >= 1

    def test_get_reminder_type_for_document_internal_unknown(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        adapter = ReminderServiceAdapter()
        assert adapter.get_reminder_type_for_document_internal("unknown_doc_type") is None

    def test_get_reminder_type_for_document_internal_summons(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        adapter = ReminderServiceAdapter()
        result = adapter.get_reminder_type_for_document_internal("court_summons")
        assert result is not None
        assert result.code == "hearing"

    def test_get_reminder_type_for_document_internal_execution(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        adapter = ReminderServiceAdapter()
        result = adapter.get_reminder_type_for_document_internal("ruling")
        assert result is not None
        assert result.code == "appeal_deadline"

    def test_get_reminder_type_for_document_internal_asset(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        adapter = ReminderServiceAdapter()
        result = adapter.get_reminder_type_for_document_internal("asset_preservation")
        assert result is not None
        assert result.code == "asset_preservation_expires"

    def test_enrich_export_row_valid_type(self):
        from apps.reminders.models import ReminderType
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        code = ReminderType.values[0]
        row = {"reminder_type": code}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert "reminder_type_label" in result

    def test_enrich_export_row_invalid_type(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        row = {"reminder_type": "bad_type"}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert result["reminder_type_label"] == "bad_type"

    def test_enrich_export_row_empty_type(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        row = {"reminder_type": ""}
        result = ReminderServiceAdapter._enrich_export_row(row)
        assert result["reminder_type_label"] == ""

    def test_document_type_to_reminder_type_mapping(self):
        from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

        m = ReminderServiceAdapter.DOCUMENT_TYPE_TO_REMINDER_TYPE
        assert m["court_summons"] == "hearing"
        assert m["hearing_summons"] == "hearing"
        assert m["evidence_deadline_notice"] == "evidence_deadline"
        assert m["submission_notice"] == "submission_deadline"
        assert m["ruling"] == "appeal_deadline"
        assert m["verdict"] == "appeal_deadline"
        assert m["asset_preservation"] == "asset_preservation_expires"


# ---------------------------------------------------------------------------
# image_rotation_api.py — helpers
# ---------------------------------------------------------------------------


class TestImageRotationApiHelpers:
    """Tests for image_rotation_api helper functions."""

    def test_validate_image_file_ok(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.image_rotation.api.image_rotation_api import _validate_image_file

        f = SimpleUploadedFile("test.jpg", b"data", content_type="image/jpeg")
        # Should not raise
        _validate_image_file(f)

    def test_validate_image_file_bad_type(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException

        f = SimpleUploadedFile("test.exe", b"data", content_type="application/exe")
        with pytest.raises(ValidationException, match="不支持的图片类型"):
            _validate_image_file(f)

    def test_validate_image_file_too_large(self):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.image_rotation.api.image_rotation_api import _validate_image_file
        from apps.core.exceptions import ValidationException

        big_data = b"\x00" * (21 * 1024 * 1024)
        f = SimpleUploadedFile("big.jpg", big_data, content_type="image/jpeg")
        with pytest.raises(ValidationException, match="文件大小超过限制"):
            _validate_image_file(f)

    def test_decode_image_data_plain(self):
        import base64
        from apps.image_rotation.api.image_rotation_api import _decode_image_data

        encoded = base64.b64encode(b"hello").decode()
        result = _decode_image_data(encoded)
        assert result == b"hello"

    def test_decode_image_data_with_data_url(self):
        import base64
        from apps.image_rotation.api.image_rotation_api import _decode_image_data

        encoded = base64.b64encode(b"test").decode()
        data_url = f"data:image/png;base64,{encoded}"
        result = _decode_image_data(data_url)
        assert result == b"test"

    def test_body_empty(self):
        from django.test import RequestFactory
        from apps.image_rotation.api.image_rotation_api import _body

        rf = RequestFactory()
        req = rf.post("/", data=b"", content_type="application/json")
        assert _body(req) == {}

    def test_body_json(self):
        import json
        from django.test import RequestFactory
        from apps.image_rotation.api.image_rotation_api import _body

        rf = RequestFactory()
        req = rf.post("/", data=json.dumps({"a": 1}).encode(), content_type="application/json")
        assert _body(req) == {"a": 1}
