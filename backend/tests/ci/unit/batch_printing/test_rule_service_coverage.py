"""batch_printing/services/execution/rule_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.batch_printing.services.execution.rule_service import RuleService


@pytest.fixture
def service() -> RuleService:
    return RuleService()


# ── get_rule ───────────────────────────────────────────────────────────


class TestGetRule:
    def test_not_found(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            MockRule.DoesNotExist = type("DoesNotExist", (Exception,), {})
            MockRule.objects.select_related.return_value.get.side_effect = MockRule.DoesNotExist()
            with pytest.raises(NotFoundError):
                service.get_rule(rule_id=999)

    def test_found(self, service: RuleService) -> None:
        rule = SimpleNamespace(id=1)
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            MockRule.objects.select_related.return_value.get.return_value = rule
            assert service.get_rule(rule_id=1) is rule


# ── delete_rule ────────────────────────────────────────────────────────


class TestDeleteRule:
    def test_success(self, service: RuleService) -> None:
        rule = MagicMock()
        rule.delete = MagicMock()
        with patch.object(service, "get_rule", return_value=rule):
            service.delete_rule(rule_id=1)
            rule.delete.assert_called_once()


# ── build_rule_payload ────────────────────────────────────────────────


class TestBuildRulePayload:
    def test_returns_dict(self, service: RuleService) -> None:
        rule = SimpleNamespace(
            id=1,
            keyword="test",
            priority=10,
            enabled=True,
            printer_name="Printer1",
            preset_snapshot_id=5,
            preset_snapshot=SimpleNamespace(preset_name="Preset1", printer_name="Printer1"),
            notes="some notes",
            created_at="2026-01-01",
            updated_at="2026-01-02",
        )
        result = service.build_rule_payload(rule=rule)
        assert result["id"] == 1
        assert result["keyword"] == "test"
        assert result["priority"] == 10
        assert result["preset_snapshot_name"] == "Preset1"
        assert result["notes"] == "some notes"

    def test_empty_notes(self, service: RuleService) -> None:
        rule = SimpleNamespace(
            id=1, keyword="k", priority=1, enabled=True,
            printer_name="p", preset_snapshot_id=1,
            preset_snapshot=SimpleNamespace(preset_name="P", printer_name="p"),
            notes=None, created_at=None, updated_at=None,
        )
        result = service.build_rule_payload(rule=rule)
        assert result["notes"] == ""


# ── sync_printer_name_from_preset ─────────────────────────────────────


class TestSyncPrinterNameFromPreset:
    def test_no_preset_id_raises(self, service: RuleService) -> None:
        rule = SimpleNamespace(preset_snapshot_id=None)
        with pytest.raises(ValidationException):
            service.sync_printer_name_from_preset(rule=rule)

    def test_syncs_printer_name(self, service: RuleService) -> None:
        preset = SimpleNamespace(id=10, printer_name="NewPrinter")
        rule = SimpleNamespace(preset_snapshot_id=10, preset_snapshot=preset, printer_name="OldPrinter")
        result = service.sync_printer_name_from_preset(rule=rule)
        assert result.printer_name == "NewPrinter"

    def test_lazy_loads_preset(self, service: RuleService) -> None:
        rule = SimpleNamespace(preset_snapshot_id=10, preset_snapshot=None, printer_name="")
        with patch("apps.batch_printing.services.execution.rule_service.PrintPresetSnapshot") as MockPreset:
            MockPreset.objects.get.return_value = SimpleNamespace(id=10, printer_name="Loaded")
            service.sync_printer_name_from_preset(rule=rule)
            assert rule.printer_name == "Loaded"


# ── find_target ────────────────────────────────────────────────────────


class TestFindTarget:
    def test_empty_filename(self, service: RuleService) -> None:
        assert service.find_target(filename="") is None
        assert service.find_target(filename=None) is None  # type: ignore[arg-type]

    def test_no_matching_rule(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            qs.filter.return_value.order_by.return_value = []
            MockRule.objects.select_related.return_value = qs
            assert service.find_target(filename="test.pdf") is None

    def test_matching_rule(self, service: RuleService) -> None:
        preset = SimpleNamespace(preset_name="P1", printer_name="Printer1")
        rule = SimpleNamespace(keyword="invoice", preset_snapshot=preset)
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            qs.filter.return_value.order_by.return_value = [rule]
            MockRule.objects.select_related.return_value = qs
            result = service.find_target(filename="invoice_2026.pdf")
            assert result is not None
            assert result[0] is rule

    def test_no_keyword_rule_skipped(self, service: RuleService) -> None:
        rule = SimpleNamespace(keyword="  ", preset_snapshot=MagicMock())
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            qs.filter.return_value.order_by.return_value = [rule]
            MockRule.objects.select_related.return_value = qs
            assert service.find_target(filename="any.pdf") is None


# ── list_rules ─────────────────────────────────────────────────────────


class TestListRules:
    def test_basic_list(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            MockRule.objects.select_related.return_value = qs
            qs.filter.return_value = qs
            qs.order_by.return_value = [1, 2]
            result = service.list_rules()
            assert result == [1, 2]

    def test_enabled_filter(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            MockRule.objects.select_related.return_value = qs
            qs.filter.return_value = qs
            qs.order_by.return_value = []
            service.list_rules(enabled=True)
            qs.filter.assert_any_call(enabled=True)

    def test_keyword_filter(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            MockRule.objects.select_related.return_value = qs
            qs.filter.return_value = qs
            qs.order_by.return_value = []
            service.list_rules(keyword="test")
            qs.filter.assert_called()

    def test_printer_name_filter(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            MockRule.objects.select_related.return_value = qs
            qs.filter.return_value = qs
            qs.order_by.return_value = []
            service.list_rules(printer_name="P1")
            qs.filter.assert_any_call(printer_name="P1")

    def test_preset_snapshot_id_filter(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintKeywordRule") as MockRule:
            qs = MagicMock()
            MockRule.objects.select_related.return_value = qs
            qs.filter.return_value = qs
            qs.order_by.return_value = []
            service.list_rules(preset_snapshot_id=3)
            qs.filter.assert_any_call(preset_snapshot_id=3)


# ── _normalize_payload ────────────────────────────────────────────────


class TestNormalizePayload:
    def test_empty_keyword_raises(self, service: RuleService) -> None:
        with pytest.raises(ValidationException):
            service._normalize_payload(payload={"keyword": ""}, partial=False)

    def test_negative_priority_raises(self, service: RuleService) -> None:
        with pytest.raises(ValidationException):
            service._normalize_payload(payload={"keyword": "test", "priority": -1, "preset_snapshot_id": 1}, partial=False)

    def test_missing_preset_raises(self, service: RuleService) -> None:
        with pytest.raises(ValidationException):
            service._normalize_payload(payload={"keyword": "test", "priority": 1, "preset_snapshot_id": None}, partial=False)

    def test_partial_keyword_only(self, service: RuleService) -> None:
        with patch("apps.batch_printing.services.execution.rule_service.PrintPresetSnapshot") as MockPreset:
            MockPreset.objects.get.return_value = SimpleNamespace(printer_name="P")
            result = service._normalize_payload(payload={"keyword": "new_kw"}, partial=True)
            assert result["keyword"] == "new_kw"

    def test_presets_loaded(self, service: RuleService) -> None:
        preset = SimpleNamespace(printer_name="P1")
        with patch("apps.batch_printing.services.execution.rule_service.PrintPresetSnapshot") as MockPreset:
            MockPreset.objects.get.return_value = preset
            result = service._normalize_payload(
                payload={"keyword": "test", "priority": 50, "enabled": True, "notes": "n", "preset_snapshot_id": 1},
                partial=False,
            )
            assert result["printer_name"] == "P1"
            assert result["preset_snapshot"] is preset
