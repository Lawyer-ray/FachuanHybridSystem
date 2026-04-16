from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.batch_printing.models import PrintKeywordRule, PrintPresetSnapshot
from apps.core.exceptions import NotFoundError, ValidationException


class RuleService:
    def list_rules(
        self,
        *,
        enabled: bool | None = None,
        keyword: str = "",
        printer_name: str = "",
        preset_snapshot_id: int | None = None,
    ) -> list[PrintKeywordRule]:
        queryset = PrintKeywordRule.objects.select_related("preset_snapshot")
        if enabled is not None:
            queryset = queryset.filter(enabled=enabled)

        normalized_printer_name = printer_name.strip()
        if normalized_printer_name:
            queryset = queryset.filter(printer_name=normalized_printer_name)

        if preset_snapshot_id is not None:
            queryset = queryset.filter(preset_snapshot_id=preset_snapshot_id)

        normalized_keyword = keyword.strip()
        if normalized_keyword:
            queryset = queryset.filter(
                Q(keyword__icontains=normalized_keyword)
                | Q(notes__icontains=normalized_keyword)
                | Q(printer_name__icontains=normalized_keyword)
                | Q(preset_snapshot__preset_name__icontains=normalized_keyword)
            )

        return list(queryset.order_by("priority", "id"))

    def get_rule(self, *, rule_id: int) -> PrintKeywordRule:
        try:
            return PrintKeywordRule.objects.select_related("preset_snapshot").get(id=rule_id)
        except PrintKeywordRule.DoesNotExist:
            raise NotFoundError(message="关键词规则不存在", code="BATCH_PRINT_RULE_NOT_FOUND", errors={}) from None

    def create_rule(self, *, payload: dict[str, Any]) -> PrintKeywordRule:
        normalized_payload = self._normalize_payload(payload=payload, partial=False)
        rule = PrintKeywordRule(**normalized_payload)
        rule.save()
        return self.get_rule(rule_id=rule.id)

    def update_rule(self, *, rule_id: int, payload: dict[str, Any]) -> PrintKeywordRule:
        rule = self.get_rule(rule_id=rule_id)
        normalized_payload = self._normalize_payload(payload=payload, partial=True)
        for field_name, value in normalized_payload.items():
            setattr(rule, field_name, value)
        self.sync_printer_name_from_preset(rule=rule)
        rule.save()
        return self.get_rule(rule_id=rule.id)

    def delete_rule(self, *, rule_id: int) -> None:
        rule = self.get_rule(rule_id=rule_id)
        rule.delete()

    def build_rule_payload(self, *, rule: PrintKeywordRule) -> dict[str, Any]:
        return {
            "id": rule.id,
            "keyword": rule.keyword,
            "priority": int(rule.priority),
            "enabled": bool(rule.enabled),
            "printer_name": rule.printer_name,
            "preset_snapshot_id": rule.preset_snapshot_id,
            "preset_snapshot_name": rule.preset_snapshot.preset_name,
            "preset_printer_name": rule.preset_snapshot.printer_name,
            "notes": rule.notes or "",
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    def sync_printer_name_from_preset(self, *, rule: PrintKeywordRule) -> PrintKeywordRule:
        if not rule.preset_snapshot_id:
            raise ValidationException(message="目标预置不能为空", errors={"preset_snapshot_id": "不能为空"})

        preset = getattr(rule, "preset_snapshot", None)
        if preset is None or getattr(preset, "id", None) != rule.preset_snapshot_id:
            preset = self._get_preset(preset_id=rule.preset_snapshot_id)
            rule.preset_snapshot = preset

        rule.printer_name = preset.printer_name
        return rule

    def find_target(self, *, filename: str) -> tuple[PrintKeywordRule, PrintPresetSnapshot] | None:
        normalized_name = (filename or "").lower()
        if not normalized_name:
            return None

        rules = (
            PrintKeywordRule.objects.select_related("preset_snapshot")
            .filter(enabled=True)
            .order_by("priority", "id")
        )
        for rule in rules:
            keyword = (rule.keyword or "").strip().lower()
            if not keyword:
                continue
            if keyword in normalized_name:
                return rule, rule.preset_snapshot
        return None

    def _normalize_payload(self, *, payload: dict[str, Any], partial: bool) -> dict[str, Any]:
        normalized: dict[str, Any] = {}

        if not partial or "keyword" in payload:
            keyword = str(payload.get("keyword", "") or "").strip()
            if not keyword:
                raise ValidationException(message="关键词不能为空", errors={"keyword": "不能为空"})
            normalized["keyword"] = keyword

        if not partial or "priority" in payload:
            priority = int(payload.get("priority", 100))
            if priority < 0:
                raise ValidationException(message="优先级不能小于 0", errors={"priority": "必须大于等于 0"})
            normalized["priority"] = priority

        if not partial or "enabled" in payload:
            normalized["enabled"] = bool(payload.get("enabled", True))

        if not partial or "notes" in payload:
            normalized["notes"] = str(payload.get("notes", "") or "").strip()

        if not partial or "preset_snapshot_id" in payload:
            raw_preset_id = payload.get("preset_snapshot_id")
            if raw_preset_id in {None, ""}:
                raise ValidationException(message="目标预置不能为空", errors={"preset_snapshot_id": "不能为空"})
            preset = self._get_preset(preset_id=int(raw_preset_id))
            normalized["preset_snapshot"] = preset
            normalized["printer_name"] = preset.printer_name

        return normalized

    def _get_preset(self, *, preset_id: int) -> PrintPresetSnapshot:
        try:
            return PrintPresetSnapshot.objects.get(id=preset_id)
        except PrintPresetSnapshot.DoesNotExist:
            raise NotFoundError(message="打印预置不存在", code="BATCH_PRINT_PRESET_NOT_FOUND", errors={}) from None
