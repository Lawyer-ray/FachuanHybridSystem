"""PresetDiscoveryService 单元测试。"""

from __future__ import annotations

from apps.batch_printing.services.preset.preset_discovery_service import PresetDiscoveryService


class TestPresetDiscoveryService:
    """验证 macOS 打印预置解析兼容不同 plist 结构。"""

    def test_collect_preset_records_supports_modern_mac_structure(self) -> None:
        service = PresetDiscoveryService()
        payload = {
            "黑白双面": {
                "com.apple.print.preset.id": "黑白双面",
                "com.apple.print.preset.settings": {
                    "number-up": "1",
                    "CNDuplex": "DuplexFront",
                },
            },
            "彩色双面": {
                "com.apple.print.preset.behavior": 0,
                "com.apple.print.preset.settings": {
                    "ColorModel": "RGB",
                },
            },
            "com.apple.print.v2.lastUsedSettingsPref": {
                "number-up": "1",
            },
        }

        records = service._collect_preset_records(payload, "canonprinter")
        record_map = {item.preset_name: item for item in records}

        assert set(record_map) == {"黑白双面", "彩色双面"}
        assert record_map["黑白双面"].printer_name == "canonprinter"
        assert record_map["黑白双面"].raw_settings["CNDuplex"] == "DuplexFront"
        assert record_map["彩色双面"].raw_settings["ColorModel"] == "RGB"

    def test_collect_preset_records_keeps_legacy_structure_compatible(self) -> None:
        service = PresetDiscoveryService()
        payload = {
            "presets": [
                {
                    "PMPresetName": "归档",
                    "PMPrintSettings": {
                        "number-up": 2,
                    },
                }
            ]
        }

        records = service._collect_preset_records(payload, "legacy_printer")

        assert len(records) == 1
        assert records[0].printer_name == "legacy_printer"
        assert records[0].preset_name == "归档"
        assert records[0].raw_settings == {"number-up": 2}
