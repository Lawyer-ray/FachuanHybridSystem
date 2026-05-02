from __future__ import annotations

from typing import Any

from django.db.models import Count, Q, QuerySet

from apps.batch_printing.models import PrintPresetSnapshot
from apps.core.exceptions import NotFoundError


class PrintPresetSnapshotService:
    def list_presets(self, *, printer_name: str = "", keyword: str = "") -> list[PrintPresetSnapshot]:
        queryset = self._base_queryset()
        normalized_printer_name = printer_name.strip()
        if normalized_printer_name:
            queryset = queryset.filter(printer_name=normalized_printer_name)

        normalized_keyword = keyword.strip()
        if normalized_keyword:
            queryset = queryset.filter(
                Q(printer_name__icontains=normalized_keyword)
                | Q(printer_display_name__icontains=normalized_keyword)
                | Q(preset_name__icontains=normalized_keyword)
                | Q(preset_source__icontains=normalized_keyword)
            )

        return list(queryset.order_by("printer_name", "preset_name", "-updated_at"))

    def get_preset(self, *, preset_id: int) -> PrintPresetSnapshot:
        try:
            return self._base_queryset().get(id=preset_id)
        except PrintPresetSnapshot.DoesNotExist:
            raise NotFoundError(message="打印预置不存在", code="BATCH_PRINT_PRESET_NOT_FOUND", errors={}) from None

    def build_preset_payload(self, *, preset: PrintPresetSnapshot) -> dict[str, Any]:
        rule_count = getattr(preset, "rule_count", None)
        if rule_count is None:
            rule_count = preset.rules.count()

        return {
            "id": preset.id,
            "printer_name": preset.printer_name,
            "printer_display_name": preset.printer_display_name or "",
            "preset_name": preset.preset_name,
            "preset_source": preset.preset_source or "",
            "raw_settings_payload": preset.raw_settings_payload or {},
            "executable_options_payload": preset.executable_options_payload or {},
            "supported_option_names": list(preset.supported_option_names or []),
            "rule_count": int(rule_count),
            "last_synced_at": preset.last_synced_at,
            "created_at": preset.created_at,
            "updated_at": preset.updated_at,
        }

    def _base_queryset(self) -> QuerySet[PrintPresetSnapshot]:
        return PrintPresetSnapshot.objects.annotate(rule_count=Count("rules", distinct=True))
