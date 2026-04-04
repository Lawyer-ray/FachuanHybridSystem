"""合同批量绑定一级文件夹服务。"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from django.db import transaction
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from apps.contracts.models import Contract, ContractTypeFolderRootPreset
from apps.contracts.services.folder.folder_binding_service import FolderBindingService
from apps.core.models.enums import CaseType
from apps.core.exceptions import ValidationException
from apps.core.infrastructure.subprocess_runner import SubprocessRunner

logger = logging.getLogger(__name__)


class ContractBatchFolderBindingService:
    """批量绑定合同文件夹（目标固定为根目录的一级子文件夹）。"""

    AUTO_SCORE_THRESHOLD = 0.72
    AUTO_SCORE_GAP = 0.08
    NON_CONTRACT_DIR_KEYWORDS = ("未成交", "归档", "模板", "示例")

    def __init__(self, *, folder_binding_service: FolderBindingService | None = None) -> None:
        self._folder_binding_service = folder_binding_service or FolderBindingService()
        self._case_type_label_map = dict(CaseType.choices)

    @property
    def folder_binding_service(self) -> FolderBindingService:
        return self._folder_binding_service

    def list_unbound_case_type_cards(self) -> list[dict[str, Any]]:
        unbound = (
            Contract.objects.filter(folder_binding__isnull=True)
            .exclude(case_type__isnull=True)
            .exclude(case_type="")
            .values("case_type")
            .annotate(unbound_count=Count("id"))
            .order_by("case_type")
        )
        preset_map = {
            item.case_type: item.root_path
            for item in ContractTypeFolderRootPreset.objects.filter(
                case_type__in=[str(row["case_type"]) for row in unbound]
            )
        }

        cards: list[dict[str, Any]] = []
        for row in unbound:
            case_type = str(row["case_type"] or "").strip()
            if not case_type:
                continue
            cards.append(
                {
                    "case_type": case_type,
                    "case_type_display": self._case_type_label_map.get(case_type, case_type),
                    "unbound_count": int(row["unbound_count"] or 0),
                    "root_path": str(preset_map.get(case_type, "") or ""),
                }
            )
        return cards

    def preview(self, *, case_type_roots: list[dict[str, Any]]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        total_contracts = 0
        auto_selected = 0

        for item in case_type_roots:
            case_type = str(item.get("case_type") or "").strip()
            root_path = str(item.get("root_path") or "").strip()
            if not case_type:
                continue

            preview_item = self._preview_single_case_type(case_type=case_type, root_path=root_path)
            items.append(preview_item)
            total_contracts += int(preview_item.get("contract_count", 0) or 0)
            auto_selected += int(preview_item.get("auto_selected_count", 0) or 0)

        return {
            "items": items,
            "summary": {
                "total_contracts": total_contracts,
                "auto_selected": auto_selected,
            },
        }

    def save(
        self,
        *,
        case_type_roots: list[dict[str, Any]],
        contract_selections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        root_map: dict[str, str] = {}
        for item in case_type_roots:
            case_type = str(item.get("case_type") or "").strip()
            root_path = str(item.get("root_path") or "").strip()
            if not case_type:
                continue
            if root_path:
                self._ensure_accessible_directory(root_path)
            root_map[case_type] = root_path
            ContractTypeFolderRootPreset.objects.update_or_create(
                case_type=case_type,
                defaults={"root_path": root_path},
            )

        bound_count = 0
        skipped_count = 0
        errors: list[str] = []

        target_ids: list[int] = []
        for item in contract_selections:
            raw_contract_id = item.get("contract_id")
            if raw_contract_id is None:
                continue
            target_ids.append(int(raw_contract_id))
        unbound_contract_map = {
            contract.id: contract
            for contract in Contract.objects.filter(id__in=target_ids, folder_binding__isnull=True).only(
                "id", "name", "case_type"
            )
        }

        with transaction.atomic():
            for item in contract_selections:
                apply_flag = bool(item.get("apply"))
                if not apply_flag:
                    skipped_count += 1
                    continue

                contract_id = int(item.get("contract_id") or 0)
                selected_folder_path = str(item.get("selected_folder_path") or "").strip()
                case_type = str(item.get("case_type") or "").strip()
                if not contract_id or not selected_folder_path:
                    skipped_count += 1
                    continue

                contract = unbound_contract_map.get(contract_id)
                if contract is None:
                    skipped_count += 1
                    errors.append(str(_("合同 %(id)s 不存在或已绑定") % {"id": contract_id}))
                    continue

                if contract.case_type != case_type:
                    skipped_count += 1
                    errors.append(str(_("合同 %(id)s 的类型已变化，请刷新后重试") % {"id": contract_id}))
                    continue

                root_path = str(root_map.get(case_type, "") or "").strip()
                if not root_path:
                    skipped_count += 1
                    errors.append(str(_("合同类型 %(type)s 缺少根目录") % {"type": case_type}))
                    continue

                try:
                    self._validate_selected_folder(root_path=root_path, selected_folder_path=selected_folder_path)
                    self.folder_binding_service.create_binding(owner_id=contract_id, folder_path=selected_folder_path)
                    bound_count += 1
                except Exception as exc:
                    skipped_count += 1
                    errors.append(str(_("合同 %(id)s 绑定失败: %(error)s") % {"id": contract_id, "error": exc}))

        return {
            "bound_count": bound_count,
            "skipped_count": skipped_count,
            "error_count": len(errors),
            "errors": errors,
        }

    def open_folder(self, *, root_path: str, folder_path: str) -> None:
        target = self._validate_selected_folder(root_path=root_path, selected_folder_path=folder_path)
        SubprocessRunner(allowed_programs={"open"}).run(
            args=["open", target.as_posix()],
            timeout_seconds=5,
            check=False,
        )

    def _preview_single_case_type(self, *, case_type: str, root_path: str) -> dict[str, Any]:
        item: dict[str, Any] = {
            "case_type": case_type,
            "case_type_display": self._case_type_label_map.get(case_type, case_type),
            "root_path": root_path,
            "contract_count": 0,
            "auto_selected_count": 0,
            "options": [],
            "rows": [],
            "error": "",
        }

        contracts = list(
            Contract.objects.filter(case_type=case_type, folder_binding__isnull=True)
            .prefetch_related("cases")
            .order_by("id")
        )
        item["contract_count"] = len(contracts)

        if not root_path:
            item["error"] = str(_("请先填写根目录"))
            return item

        try:
            root = self._ensure_accessible_directory(root_path)
            candidates = self._list_first_level_dirs(root)
        except Exception as exc:
            item["error"] = str(exc)
            return item

        item["options"] = [
            {"name": folder.name, "path": folder.as_posix(), "is_penalized": self._is_non_contract_dir(folder.name)}
            for folder in candidates
        ]

        rows: list[dict[str, Any]] = []
        auto_selected_count = 0
        for contract in contracts:
            case_names = [str(case.name or "").strip() for case in contract.cases.all() if str(case.name or "").strip()]
            case_filing_numbers = [
                str(case.filing_number or "").strip() for case in contract.cases.all() if str(case.filing_number or "").strip()
            ]
            recommend = self._recommend_folder(
                contract_name=str(contract.name or ""),
                contract_filing_number=str(contract.filing_number or ""),
                oa_case_number=str(contract.law_firm_oa_case_number or ""),
                case_names=case_names,
                case_filing_numbers=case_filing_numbers,
                candidates=candidates,
            )

            selected_folder_path = str(recommend.get("recommended_folder_path") or "")
            auto_selected_flag = bool(recommend.get("auto_selected")) and bool(selected_folder_path)
            if auto_selected_flag:
                auto_selected_count += 1

            rows.append(
                {
                    "contract_id": contract.id,
                    "case_type": case_type,
                    "contract_name": contract.name,
                    "case_names": case_names,
                    "filing_number": str(contract.filing_number or ""),
                    "oa_case_number": str(contract.law_firm_oa_case_number or ""),
                    "recommended_folder_path": selected_folder_path,
                    "recommended_folder_name": str(recommend.get("recommended_folder_name") or ""),
                    "confidence": float(recommend.get("confidence") or 0.0),
                    "reason": str(recommend.get("reason") or ""),
                    "auto_selected": auto_selected_flag,
                    "selected_folder_path": selected_folder_path,
                    "apply": auto_selected_flag,
                    "candidates": recommend.get("candidates", []),
                }
            )

        item["rows"] = rows
        item["auto_selected_count"] = auto_selected_count
        return item

    def _recommend_folder(
        self,
        *,
        contract_name: str,
        contract_filing_number: str,
        oa_case_number: str,
        case_names: list[str],
        case_filing_numbers: list[str],
        candidates: list[Path],
    ) -> dict[str, Any]:
        targets: list[tuple[str, str, float]] = []
        if contract_name:
            targets.append((contract_name, str(_("合同名称")), 1.0))
        for name in case_names:
            targets.append((name, str(_("案件名称")), 1.0))
        if contract_filing_number:
            targets.append((contract_filing_number, str(_("合同建档编号")), 0.95))
        if oa_case_number:
            targets.append((oa_case_number, str(_("律所OA案件编号")), 1.0))
        for number in case_filing_numbers:
            targets.append((number, str(_("案件建档编号")), 0.95))

        scored_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            score_data = self._score_candidate(candidate_name=candidate.name, targets=targets)
            score = float(score_data.get("score") or 0.0)
            if self._is_non_contract_dir(candidate.name):
                score = max(0.0, score - 0.25)
            scored_candidates.append(
                {
                    "path": candidate.as_posix(),
                    "name": candidate.name,
                    "score": round(score, 4),
                    "reason": str(score_data.get("reason") or ""),
                }
            )

        scored_candidates.sort(key=lambda row: (-float(row["score"]), str(row["name"])))
        if not scored_candidates:
            return {
                "recommended_folder_path": "",
                "recommended_folder_name": "",
                "confidence": 0.0,
                "reason": str(_("未找到一级子文件夹")),
                "auto_selected": False,
                "candidates": [],
            }

        top = scored_candidates[0]
        second_score = float(scored_candidates[1]["score"]) if len(scored_candidates) > 1 else 0.0
        top_score = float(top["score"])
        auto_selected = top_score >= self.AUTO_SCORE_THRESHOLD and (top_score - second_score) >= self.AUTO_SCORE_GAP

        return {
            "recommended_folder_path": str(top["path"]) if auto_selected else "",
            "recommended_folder_name": str(top["name"]) if auto_selected else "",
            "confidence": top_score,
            "reason": str(top["reason"]),
            "auto_selected": auto_selected,
            "candidates": scored_candidates,
        }

    def _score_candidate(self, *, candidate_name: str, targets: list[tuple[str, str, float]]) -> dict[str, Any]:
        candidate_norm = self._normalize_text(candidate_name)
        candidate_alias = self._normalize_alias(candidate_name)
        best_score = 0.0
        best_reason = ""

        for target_value, target_label, target_weight in targets:
            target_norm = self._normalize_text(target_value)
            target_alias = self._normalize_alias(target_value)
            if not target_norm and not target_alias:
                continue

            ratio_norm = self._sequence_ratio(candidate_norm, target_norm)
            ratio_alias = self._sequence_ratio(candidate_alias, target_alias)
            base_score = max(ratio_norm, ratio_alias)

            contains_bonus = 0.0
            if candidate_norm and target_norm and (candidate_norm in target_norm or target_norm in candidate_norm):
                contains_bonus = 0.12

            number_bonus = 0.0
            if self._looks_like_number(target_value) and target_value in candidate_name:
                number_bonus = 0.3

            score = min(1.0, (base_score + contains_bonus + number_bonus) * float(target_weight))
            if score > best_score:
                best_score = score
                best_reason = str(_("命中%(label)s") % {"label": target_label})

        return {"score": best_score, "reason": best_reason}

    def _validate_selected_folder(self, *, root_path: str, selected_folder_path: str) -> Path:
        root = self._ensure_accessible_directory(root_path)
        target = self._ensure_accessible_directory(selected_folder_path)

        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValidationException(message=_("选择目录不在根目录范围内")) from exc

        if target.parent != root:
            raise ValidationException(message=_("只能绑定根目录下的一级子文件夹"))
        return target

    def _ensure_accessible_directory(self, folder_path: str) -> Path:
        path = Path(folder_path).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValidationException(message=_("目录不可访问: %(path)s") % {"path": folder_path})
        return path

    def _list_first_level_dirs(self, root: Path) -> list[Path]:
        dirs = [item.resolve() for item in root.iterdir() if item.is_dir() and not item.name.startswith(".")]
        dirs.sort(key=lambda folder: folder.name.lower())
        return dirs

    def _normalize_text(self, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = self._strip_leading_date(text)
        text = self._strip_leading_labels(text)
        text = re.sub(r"[（）()【】\[\]{}]", " ", text)
        text = re.sub(r"[，。、“”‘’；：,.!?！？\-_/\\|]", " ", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def _normalize_alias(self, value: str) -> str:
        text = self._normalize_text(value)
        for token in (
            "股份有限公司",
            "有限责任公司",
            "有限公司",
            "有限合伙",
            "公司",
            "一案",
            "二案",
            "三案",
            "四案",
            "系列案",
            "案件",
            "案",
        ):
            text = text.replace(token.lower(), "")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _strip_leading_date(self, text: str) -> str:
        return re.sub(r"^\d{4}[.\-_]\d{1,2}[.\-_]\d{1,2}\s*[-_－]?\s*", "", text)

    def _strip_leading_labels(self, text: str) -> str:
        value = text
        while True:
            updated = re.sub(r"^\[[^\]]+\]\s*", "", value)
            if updated == value:
                break
            value = updated
        return value

    def _looks_like_number(self, value: str) -> bool:
        raw = str(value or "").strip()
        if not raw:
            return False
        return any(char.isdigit() for char in raw)

    def _sequence_ratio(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return float(SequenceMatcher(None, left, right).ratio())

    def _is_non_contract_dir(self, folder_name: str) -> bool:
        return any(keyword in str(folder_name or "") for keyword in self.NON_CONTRACT_DIR_KEYWORDS)
