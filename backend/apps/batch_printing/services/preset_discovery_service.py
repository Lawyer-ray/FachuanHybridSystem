from __future__ import annotations

import logging
import plistlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.utils import timezone

from apps.batch_printing.models import PrintPresetSnapshot

logger = logging.getLogger("apps.batch_printing")

_PRESET_FILENAME_PREFIX = "com.apple.print.custompresets.forprinter."
_PRESET_FILENAME_SUFFIX = ".plist"
_PRESET_METADATA_PREFIX = "com.apple.print."
_PRESET_SETTINGS_KEY = "com.apple.print.preset.settings"
_PRESET_ID_KEY = "com.apple.print.preset.id"


@dataclass
class PresetRecord:
    printer_name: str
    preset_name: str
    raw_settings: dict[str, Any]


class PresetDiscoveryService:
    preferences_dir = Path.home() / "Library" / "Preferences"

    def sync_presets(self) -> dict[str, int]:
        records = self.discover_presets()
        upserted = 0
        now = timezone.now()

        for record in records:
            supported_options = sorted(self._read_supported_options(record.printer_name))
            executable_options = self._extract_executable_options(record.raw_settings, set(supported_options))

            PrintPresetSnapshot.objects.update_or_create(
                printer_name=record.printer_name,
                preset_name=record.preset_name,
                defaults={
                    "printer_display_name": record.printer_name,
                    "preset_source": "mac_plist",
                    "raw_settings_payload": record.raw_settings,
                    "executable_options_payload": executable_options,
                    "supported_option_names": supported_options,
                    "last_synced_at": now,
                },
            )
            upserted += 1

        return {"discovered": len(records), "upserted": upserted}

    def discover_presets(self) -> list[PresetRecord]:
        records: list[PresetRecord] = []
        if not self.preferences_dir.exists():
            return records

        for plist_path in sorted(self.preferences_dir.glob(f"{_PRESET_FILENAME_PREFIX}*{_PRESET_FILENAME_SUFFIX}")):
            printer_name = self._extract_printer_name(plist_path)
            if not printer_name:
                continue
            parsed = self._load_plist(plist_path)
            if parsed is None:
                continue
            records.extend(self._collect_preset_records(parsed, printer_name))

        return records

    def _extract_printer_name(self, plist_path: Path) -> str:
        name = plist_path.name
        if not name.startswith(_PRESET_FILENAME_PREFIX) or not name.endswith(_PRESET_FILENAME_SUFFIX):
            return ""
        token = name.removeprefix(_PRESET_FILENAME_PREFIX).removesuffix(_PRESET_FILENAME_SUFFIX)
        return token.strip()

    def _load_plist(self, plist_path: Path) -> Any | None:
        try:
            with plist_path.open("rb") as fp:
                return plistlib.load(fp)
        except Exception:
            logger.exception("batch_printing_plist_parse_failed", extra={"path": str(plist_path)})
            return None

    def _collect_preset_records(self, payload: Any, printer_name: str) -> list[PresetRecord]:
        records: list[PresetRecord] = []
        self._walk_preset_nodes(payload, printer_name=printer_name, records=records)

        dedup: dict[tuple[str, str], PresetRecord] = {}
        for item in records:
            key = (item.printer_name, item.preset_name)
            dedup[key] = item
        return list(dedup.values())

    def _walk_preset_nodes(self, node: Any, *, printer_name: str, records: list[PresetRecord]) -> None:
        if isinstance(node, dict):
            self._append_legacy_preset_record(node, printer_name=printer_name, records=records)
            self._append_modern_preset_records(node, printer_name=printer_name, records=records)
            for child in node.values():
                self._walk_preset_nodes(child, printer_name=printer_name, records=records)
            return

        if isinstance(node, list):
            for item in node:
                self._walk_preset_nodes(item, printer_name=printer_name, records=records)

    def _append_legacy_preset_record(
        self,
        node: dict[str, Any],
        *,
        printer_name: str,
        records: list[PresetRecord],
    ) -> None:
        preset_name = node.get("PMPresetName")
        print_settings = node.get("PMPrintSettings")
        if isinstance(preset_name, str) and isinstance(print_settings, dict):
            self._append_record(
                printer_name=printer_name,
                preset_name=preset_name,
                raw_settings=print_settings,
                records=records,
            )

    def _append_modern_preset_records(
        self,
        node: dict[str, Any],
        *,
        printer_name: str,
        records: list[PresetRecord],
    ) -> None:
        for key, value in node.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            if key.startswith(_PRESET_METADATA_PREFIX):
                continue

            raw_settings = value.get(_PRESET_SETTINGS_KEY)
            if not isinstance(raw_settings, dict):
                continue

            preset_id = value.get(_PRESET_ID_KEY)
            preset_name = preset_id if isinstance(preset_id, str) and preset_id.strip() else key
            self._append_record(
                printer_name=printer_name,
                preset_name=preset_name,
                raw_settings=raw_settings,
                records=records,
            )

    def _append_record(
        self,
        *,
        printer_name: str,
        preset_name: str,
        raw_settings: dict[str, Any],
        records: list[PresetRecord],
    ) -> None:
        normalized_name = (preset_name or "").strip()
        if not normalized_name:
            return

        records.append(
            PresetRecord(
                printer_name=printer_name,
                preset_name=normalized_name,
                raw_settings=raw_settings,
            )
        )

    def _read_supported_options(self, printer_name: str) -> set[str]:
        command = ["lpoptions", "-p", printer_name, "-l"]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return set()

        option_names: set[str] = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            name = line.split(":", 1)[0].strip()
            if not name:
                continue
            option_names.add(name)

        return option_names

    def _extract_executable_options(self, raw_settings: dict[str, Any], supported_option_names: set[str]) -> dict[str, str]:
        executable: dict[str, str] = {}
        for key, value in raw_settings.items():
            normalized = str(key).strip()
            if not normalized:
                continue
            if supported_option_names and normalized not in supported_option_names:
                if normalized not in {"number-up", "sides"}:
                    continue
            value_text = self._normalize_option_value(value)
            if value_text:
                executable[normalized] = value_text
        return executable

    def _normalize_option_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="ignore").strip()
            except Exception:
                return ""
        text = str(value).strip()
        text = re.sub(r"\s+", " ", text)
        return text
