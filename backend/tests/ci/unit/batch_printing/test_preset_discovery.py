"""批量打印预设发现服务测试。"""

from __future__ import annotations

from pathlib import Path
from apps.batch_printing.services.preset.preset_discovery_service import (
    PresetDiscoveryService,
    PresetRecord,
    _PRESET_FILENAME_PREFIX,
    _PRESET_FILENAME_SUFFIX,
)


class TestPresetRecord:
    """PresetRecord 数据类测试。"""

    def test_creation(self) -> None:
        record = PresetRecord(
            printer_name="HP_LaserJet",
            preset_name="双面打印",
            raw_settings={"Duplex": True},
        )
        assert record.printer_name == "HP_LaserJet"
        assert record.preset_name == "双面打印"
        assert record.raw_settings["Duplex"] is True


class TestPresetDiscoveryService:
    """PresetDiscoveryService 测试。"""

    def setup_method(self) -> None:
        self.service = PresetDiscoveryService()

    def test_extract_printer_name_valid(self) -> None:
        """有效 plist 文件名。"""
        path = Path(f"{_PRESET_FILENAME_PREFIX}HP_LaserJet{_PRESET_FILENAME_SUFFIX}")
        name = self.service._extract_printer_name(path)
        assert name == "HP_LaserJet"

    def test_extract_printer_name_invalid_prefix(self) -> None:
        """无效前缀。"""
        path = Path("invalid_prefix_HP.plist")
        name = self.service._extract_printer_name(path)
        assert name == ""

    def test_extract_printer_name_invalid_suffix(self) -> None:
        """无效后缀。"""
        path = Path(f"{_PRESET_FILENAME_PREFIX}HP_LaserJet.txt")
        name = self.service._extract_printer_name(path)
        assert name == ""

    def test_extract_printer_name_with_spaces(self) -> None:
        """文件名包含空格。"""
        path = Path(f"{_PRESET_FILENAME_PREFIX} HP LaserJet {_PRESET_FILENAME_SUFFIX}")
        name = self.service._extract_printer_name(path)
        assert name == "HP LaserJet"

    def test_collect_preset_records_legacy(self) -> None:
        """收集旧格式预设记录。"""
        payload = {
            "PMPresetName": "双面打印",
            "PMPrintSettings": {"Duplex": True, "PaperSize": "A4"},
        }
        records = self.service._collect_preset_records(payload, "HP_LaserJet")
        assert len(records) == 1
        assert records[0].preset_name == "双面打印"
        assert records[0].raw_settings["Duplex"] is True

    def test_collect_preset_records_modern(self) -> None:
        """收集新格式预设记录。"""
        payload = {
            "my_preset": {
                "com.apple.print.preset.settings": {"Duplex": True},
                "com.apple.print.preset.id": "preset_001",
            },
        }
        records = self.service._collect_preset_records(payload, "HP_LaserJet")
        assert len(records) == 1
        assert records[0].preset_name == "preset_001"

    def test_collect_preset_records_modern_no_id(self) -> None:
        """新格式无 preset id，使用 key 作为名称。"""
        payload = {
            "my_preset": {
                "com.apple.print.preset.settings": {"Duplex": True},
            },
        }
        records = self.service._collect_preset_records(payload, "HP_LaserJet")
        assert len(records) == 1
        assert records[0].preset_name == "my_preset"

    def test_collect_preset_records_dedup(self) -> None:
        """去重预设记录。"""
        payload = {
            "PMPresetName": "双面打印",
            "PMPrintSettings": {"Duplex": True},
        }
        # 重复调用应该去重
        records = self.service._collect_preset_records(payload, "HP_LaserJet")
        assert len(records) == 1

    def test_collect_preset_records_empty(self) -> None:
        """空 payload。"""
        records = self.service._collect_preset_records({}, "HP_LaserJet")
        assert len(records) == 0

    def test_collect_preset_records_nested(self) -> None:
        """嵌套 payload。"""
        payload = {
            "outer": {
                "inner": {
                    "PMPresetName": "测试预设",
                    "PMPrintSettings": {"PaperSize": "A4"},
                },
            },
        }
        records = self.service._collect_preset_records(payload, "HP_LaserJet")
        assert len(records) == 1
        assert records[0].preset_name == "测试预设"

    def test_load_plist_invalid(self) -> None:
        """无效 plist 文件返回 None。"""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".plist", mode="wb", delete=False) as f:
            f.write(b"not a valid plist")
            f.flush()
            result = self.service._load_plist(Path(f.name))
            assert result is None

    def test_discover_presets_no_dir(self) -> None:
        """偏好设置目录不存在返回空列表。"""
        import tempfile

        self.service.preferences_dir = Path(tempfile.mkdtemp()) / "nonexistent"
        result = self.service.discover_presets()
        assert result == []
