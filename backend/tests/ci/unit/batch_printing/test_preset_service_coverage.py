"""补充覆盖测试: batch_printing/services/preset/preset_service.py

覆盖: list_presets 的打印机名/关键词过滤与排序、get_preset 的
NotFoundError、build_preset_payload 的 rule_count 回退与空默认值。
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.batch_printing.models import PrintKeywordRule, PrintPresetSnapshot
from apps.batch_printing.services.preset.preset_service import PrintPresetSnapshotService
from apps.core.exceptions import NotFoundError


def _create_preset(
    *,
    printer_name: str,
    preset_name: str,
    display_name: str = "",
    preset_source: str = "",
) -> PrintPresetSnapshot:
    return PrintPresetSnapshot.objects.create(
        printer_name=printer_name,
        preset_name=preset_name,
        printer_display_name=display_name,
        preset_source=preset_source,
        raw_settings_payload={"dpi": 600},
        executable_options_payload={"copies": 1},
        supported_option_names=["dpi", "copies"],
        last_synced_at=timezone.now(),
    )


@pytest.mark.django_db
class TestListPresets:
    def test_lists_all_ordered_by_printer_and_preset(self):
        _create_preset(printer_name="HP", preset_name="默认")
        _create_preset(printer_name="Canon", preset_name="高质量")
        _create_preset(printer_name="HP", preset_name="草稿")
        result = PrintPresetSnapshotService().list_presets()
        pairs = [(p.printer_name, p.preset_name) for p in result]
        assert pairs == [("Canon", "高质量"), ("HP", "草稿"), ("HP", "默认")]

    def test_filter_by_printer_name(self):
        _create_preset(printer_name="HP", preset_name="默认")
        _create_preset(printer_name="Canon", preset_name="高质量")
        result = PrintPresetSnapshotService().list_presets(printer_name="HP")
        assert [p.printer_name for p in result] == ["HP"]

    def test_printer_name_filter_strips_whitespace(self):
        _create_preset(printer_name="HP", preset_name="默认")
        result = PrintPresetSnapshotService().list_presets(printer_name="  HP  ")
        assert len(result) == 1

    def test_keyword_matches_display_name(self):
        _create_preset(printer_name="HP", preset_name="默认", display_name="惠普激光")
        _create_preset(printer_name="Canon", preset_name="高质量", display_name="佳能")
        result = PrintPresetSnapshotService().list_presets(keyword="惠普")
        assert [p.printer_name for p in result] == ["HP"]

    def test_keyword_matches_preset_source(self):
        _create_preset(printer_name="HP", preset_name="默认", preset_source="system_default")
        _create_preset(printer_name="Canon", preset_name="高质量", preset_source="user_saved")
        result = PrintPresetSnapshotService().list_presets(keyword="system")
        assert [p.printer_name for p in result] == ["HP"]

    def test_keyword_matches_printer_name(self):
        _create_preset(printer_name="HP-LaserJet", preset_name="默认")
        _create_preset(printer_name="Canon", preset_name="高质量")
        result = PrintPresetSnapshotService().list_presets(keyword="laserjet")
        assert [p.printer_name for p in result] == ["HP-LaserJet"]

    def test_keyword_matches_preset_name(self):
        _create_preset(printer_name="HP", preset_name="双面彩色")
        _create_preset(printer_name="HP", preset_name="单面黑白")
        result = PrintPresetSnapshotService().list_presets(keyword="彩色")
        assert [p.preset_name for p in result] == ["双面彩色"]

    def test_no_match_returns_empty(self):
        _create_preset(printer_name="HP", preset_name="默认")
        assert PrintPresetSnapshotService().list_presets(keyword="不存在的关键词") == []

    def test_whitespace_only_keyword_returns_all(self):
        _create_preset(printer_name="HP", preset_name="默认")
        result = PrintPresetSnapshotService().list_presets(keyword="   ")
        assert len(result) == 1

    def test_combined_printer_and_keyword(self):
        _create_preset(printer_name="HP", preset_name="双面", display_name="惠普双面")
        _create_preset(printer_name="HP", preset_name="单面", display_name="惠普单面")
        _create_preset(printer_name="Canon", preset_name="双面", display_name="佳能双面")
        result = PrintPresetSnapshotService().list_presets(printer_name="HP", keyword="双面")
        assert [(p.printer_name, p.preset_name) for p in result] == [("HP", "双面")]


@pytest.mark.django_db
class TestGetPreset:
    def test_found(self):
        preset = _create_preset(printer_name="HP", preset_name="默认")
        result = PrintPresetSnapshotService().get_preset(preset_id=preset.id)
        assert result.id == preset.id
        assert result.rule_count == 0  # 无规则时注解为 0

    def test_not_found_raises_with_code(self):
        with pytest.raises(NotFoundError) as exc_info:
            PrintPresetSnapshotService().get_preset(preset_id=999999)
        assert exc_info.value.code == "BATCH_PRINT_PRESET_NOT_FOUND"


@pytest.mark.django_db
class TestBuildPresetPayload:
    def test_full_payload_with_annotation(self):
        preset = _create_preset(printer_name="HP", preset_name="默认", display_name="惠普", preset_source="system")
        PrintKeywordRule.objects.create(keyword="起诉状", printer_name="HP", preset_snapshot=preset, priority=10)
        PrintKeywordRule.objects.create(keyword="答辩状", printer_name="HP", preset_snapshot=preset, priority=20)
        fetched = PrintPresetSnapshotService().get_preset(preset_id=preset.id)
        payload = PrintPresetSnapshotService().build_preset_payload(preset=fetched)
        assert payload["id"] == preset.id
        assert payload["printer_name"] == "HP"
        assert payload["printer_display_name"] == "惠普"
        assert payload["preset_name"] == "默认"
        assert payload["preset_source"] == "system"
        assert payload["raw_settings_payload"] == {"dpi": 600}
        assert payload["executable_options_payload"] == {"copies": 1}
        assert payload["supported_option_names"] == ["dpi", "copies"]
        assert payload["rule_count"] == 2
        assert payload["last_synced_at"] == preset.last_synced_at

    def test_payload_without_annotation_falls_back_to_count(self):
        """绕过注解（如手工构造的实例）时回退 preset.rules.count()。"""
        preset = _create_preset(printer_name="Canon", preset_name="高质量")
        PrintKeywordRule.objects.create(keyword="证据清单", printer_name="Canon", preset_snapshot=preset)
        fresh = PrintPresetSnapshot.objects.get(id=preset.id)  # 无 rule_count 注解
        assert not hasattr(fresh, "rule_count")
        payload = PrintPresetSnapshotService().build_preset_payload(preset=fresh)
        assert payload["rule_count"] == 1

    def test_empty_defaults_normalized(self):
        PrintPresetSnapshot.objects.create(
            printer_name="Epson",
            preset_name="快速",
            last_synced_at=timezone.now(),
        )
        fresh = PrintPresetSnapshot.objects.get(printer_name="Epson")
        payload = PrintPresetSnapshotService().build_preset_payload(preset=fresh)
        assert payload["printer_display_name"] == ""
        assert payload["preset_source"] == ""
        assert payload["raw_settings_payload"] == {}
        assert payload["executable_options_payload"] == {}
        assert payload["supported_option_names"] == []
        assert payload["rule_count"] == 0
