from __future__ import annotations

import logging
import re
from typing import Any

from .constants import (
    EXECUTION_TARGET_ALLOWED_CODES,
    EXECUTION_TARGET_CODE_BEHAVIOR,
    EXECUTION_TARGET_CODE_IMMOVABLE,
    EXECUTION_TARGET_CODE_MONEY,
    EXECUTION_TARGET_CODE_MOVABLE,
    EXECUTION_TARGET_CODE_PROPERTY_RIGHT,
)

logger = logging.getLogger("plugins.court_filing_http")

class ExecutionValidationMixin:
    @staticmethod
    def _normalize_name(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or "").strip())

    @staticmethod
    def _first_non_empty(record: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = str(record.get(key) or "").strip()
            if value:
                return value
        return ""

    def _find_record_by_name(
        self,
        records: list[dict[str, Any]],
        *,
        expected_name: str,
        name_keys: tuple[str, ...],
    ) -> dict[str, Any] | None:
        target = self._normalize_name(expected_name)
        if not target:
            return None
        for record in records:
            for key in name_keys:
                current = self._normalize_name(record.get(key))
                if current and current == target:
                    return record
        return None

    def _ensure_written(
        self,
        *,
        expected_value: str,
        record: dict[str, Any],
        actual_keys: tuple[str, ...],
        issue: str,
        issues: list[str],
    ) -> None:
        if not str(expected_value or "").strip():
            return
        if self._first_non_empty(record, actual_keys):
            return
        issues.append(issue)

    @staticmethod
    def _parse_execution_target_codes(raw_value: Any) -> list[str]:
        if raw_value is None:
            return []

        raw_items: list[str] = []
        if isinstance(raw_value, (list, tuple, set)):
            raw_items = [str(item or "").strip() for item in raw_value]
        else:
            text = str(raw_value or "").strip()
            if text:
                raw_items = [item.strip() for item in text.split(",")]

        alias_to_code = {
            "money": EXECUTION_TARGET_CODE_MONEY,
            "cash": EXECUTION_TARGET_CODE_MONEY,
            "amount": EXECUTION_TARGET_CODE_MONEY,
            "金钱给付": EXECUTION_TARGET_CODE_MONEY,
            "behavior": EXECUTION_TARGET_CODE_BEHAVIOR,
            "行为": EXECUTION_TARGET_CODE_BEHAVIOR,
            "property_right": EXECUTION_TARGET_CODE_PROPERTY_RIGHT,
            "property-right": EXECUTION_TARGET_CODE_PROPERTY_RIGHT,
            "财产性权益": EXECUTION_TARGET_CODE_PROPERTY_RIGHT,
            "movable": EXECUTION_TARGET_CODE_MOVABLE,
            "动产": EXECUTION_TARGET_CODE_MOVABLE,
            "immovable": EXECUTION_TARGET_CODE_IMMOVABLE,
            "real_estate": EXECUTION_TARGET_CODE_IMMOVABLE,
            "real-estate": EXECUTION_TARGET_CODE_IMMOVABLE,
            "不动产": EXECUTION_TARGET_CODE_IMMOVABLE,
        }

        normalized: list[str] = []
        for raw in raw_items:
            if not raw:
                continue
            key = raw.lower()
            candidate = alias_to_code.get(key) or alias_to_code.get(raw) or raw
            if candidate not in EXECUTION_TARGET_ALLOWED_CODES:
                continue
            if candidate in normalized:
                continue
            normalized.append(candidate)
        return normalized

    def _resolve_execution_target_codes(self, case_data: dict[str, Any], *, amount: str = "") -> list[str]:
        candidate_values: list[Any] = [
            case_data.get("execution_target_codes"),
            case_data.get("execution_target_types"),
            case_data.get("execution_target_type_codes"),
            case_data.get("execution_target_type"),
            case_data.get("execution_target"),
        ]

        for value in candidate_values:
            parsed = self._parse_execution_target_codes(value)
            if parsed:
                return parsed

        if amount:
            return [EXECUTION_TARGET_CODE_MONEY]
        return [EXECUTION_TARGET_CODE_MONEY]

    async def _validate_written_payload(
        self: Any,
        *,
        layyid: str,
        case_data: dict[str, Any],
        detail: dict[str, Any],
        is_exec: bool,
        execution_target_updated_keys: set[str] | None = None,
    ) -> None:
        issues: list[str] = []
        dsr_records = [row for row in (detail.get("dsr") or detail.get("dsrs") or []) if isinstance(row, dict)]
        dlr_records = [row for row in (detail.get("dlr") or detail.get("dlrs") or []) if isinstance(row, dict)]

        expected_parties: list[dict[str, Any]] = []
        expected_parties.extend([p for p in case_data.get("plaintiffs", []) if isinstance(p, dict)])
        expected_parties.extend([p for p in case_data.get("defendants", []) if isinstance(p, dict)])
        expected_parties.extend([p for p in case_data.get("third_parties", []) if isinstance(p, dict)])

        if dsr_records and expected_parties:
            for party in expected_parties:
                expected_name = str(party.get("name") or "").strip()
                if not expected_name:
                    continue
                matched = self._find_record_by_name(
                    dsr_records,
                    expected_name=expected_name,
                    name_keys=("xm", "dwmc", "name", "mc"),
                )
                if matched is None:
                    issues.append(f"当事人未写入: {expected_name}")
                    continue

                if str(party.get("client_type") or "") == "natural":
                    self._ensure_written(
                        expected_value=str(party.get("id_number") or ""),
                        record=matched,
                        actual_keys=("zjhm", "idNumber", "sfzh"),
                        issue=f"自然人证件号缺失: {expected_name}",
                        issues=issues,
                    )
                    self._ensure_written(
                        expected_value=str(party.get("address") or ""),
                        record=matched,
                        actual_keys=("dz", "hjszd", "zsd", "address"),
                        issue=f"自然人地址缺失: {expected_name}",
                        issues=issues,
                    )
                    self._ensure_written(
                        expected_value=str(party.get("phone") or ""),
                        record=matched,
                        actual_keys=("sjhm", "lxdh", "phone"),
                        issue=f"自然人联系电话缺失: {expected_name}",
                        issues=issues,
                    )
                else:
                    self._ensure_written(
                        expected_value=str(party.get("uscc") or ""),
                        record=matched,
                        actual_keys=("zzhm", "uscc"),
                        issue=f"法人统一社会信用代码缺失: {expected_name}",
                        issues=issues,
                    )
                    self._ensure_written(
                        expected_value=str(party.get("legal_rep") or ""),
                        record=matched,
                        actual_keys=("fddbrxm", "fddbr", "legalRep"),
                        issue=f"法人法定代表人缺失: {expected_name}",
                        issues=issues,
                    )

        expected_agents = [item for item in case_data.get("agents", []) if isinstance(item, dict)]
        single_agent = case_data.get("agent")
        if not expected_agents and isinstance(single_agent, dict):
            expected_agents = [single_agent]

        if dlr_records and expected_agents:
            matched_agents: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for agent in expected_agents:
                expected_name = str(agent.get("name") or "").strip()
                if not expected_name:
                    continue
                matched = self._find_record_by_name(
                    dlr_records,
                    expected_name=expected_name,
                    name_keys=("xm", "name"),
                )
                if matched is None:
                    continue
                matched_agents.append((agent, matched))

            if not matched_agents:
                fallback_name = str((expected_agents[0] or {}).get("name") or "").strip() or "首位代理人"
                issues.append(f"代理人未写入: {fallback_name}")
            else:
                agent, matched = matched_agents[0]
                expected_name = str(agent.get("name") or "").strip() or "代理人"
                self._ensure_written(
                    expected_value=str(agent.get("id_number") or ""),
                    record=matched,
                    actual_keys=("zjhm", "idNumber", "sfzh"),
                    issue=f"代理人证件号缺失: {expected_name}",
                    issues=issues,
                )
                self._ensure_written(
                    expected_value=str(agent.get("phone") or ""),
                    record=matched,
                    actual_keys=("sjhm", "lxdh", "phone"),
                    issue=f"代理人联系电话缺失: {expected_name}",
                    issues=issues,
                )
                self._ensure_written(
                    expected_value=str(agent.get("bar_number") or ""),
                    record=matched,
                    actual_keys=("zyzh", "barNo"),
                    issue=f"代理人执业证号缺失: {expected_name}",
                    issues=issues,
                )
                self._ensure_written(
                    expected_value=str(agent.get("law_firm") or ""),
                    record=matched,
                    actual_keys=("zyjg", "lawFirm"),
                    issue=f"代理人执业机构缺失: {expected_name}",
                    issues=issues,
                )

        if is_exec:
            execution_reason = str(case_data.get("execution_reason") or "").strip()
            execution_request = str(case_data.get("execution_request") or "").strip()
            execution_amount = str(case_data.get("target_amount") or "").strip()
            jbxx = await self._get_jbxx(layyid)
            reason_keys = {"zxyy", "zxly", "zxyjzw"}
            request_keys = {"zxqq", "sqzxsx", "zxqs", "zxqqnr"}
            updated_keys = {str(item).strip() for item in (execution_target_updated_keys or set()) if str(item).strip()}
            zxxs_records = [row for row in (detail.get("zxxses") or detail.get("zxxs") or []) if isinstance(row, dict)]
            zxyj_records = [row for row in (detail.get("zxyjs") or detail.get("zxyj") or []) if isinstance(row, dict)]
            expected_target_codes = set(self._resolve_execution_target_codes(case_data, amount=execution_amount))

            has_reason = (
                bool(self._first_non_empty(jbxx, tuple(reason_keys)))
                or any(bool(self._first_non_empty(record, tuple(reason_keys))) for record in zxxs_records)
                or any(bool(self._first_non_empty(record, tuple(reason_keys))) for record in zxyj_records)
            )
            has_request = (
                bool(self._first_non_empty(jbxx, tuple(request_keys)))
                or any(bool(self._first_non_empty(record, tuple(request_keys))) for record in zxxs_records)
                or any(bool(self._first_non_empty(record, tuple(request_keys))) for record in zxyj_records)
            )

            if execution_reason and not has_reason:
                issues.append("执行理由未写入")
            if execution_request and not has_request:
                issues.append("执行请求未写入")

            persisted_target_codes: set[str] = set()
            for record in [jbxx, *zxyj_records]:
                persisted_target_codes.update(self._parse_execution_target_codes(record.get("sqzxbdzl")))

            if expected_target_codes and not persisted_target_codes.intersection(expected_target_codes):
                issues.append("执行标的类型未写入")

            has_exec_amount = bool(self._first_non_empty(jbxx, ("sqzxbdje", "sqbdje"))) or any(
                bool(self._first_non_empty(record, ("sqzxbdje", "sqbdje"))) for record in zxyj_records
            )

            if execution_amount and EXECUTION_TARGET_CODE_MONEY in expected_target_codes and not has_exec_amount:
                issues.append("申请执行标的金额未写入")

            if issues and updated_keys:
                logger.warning(
                    "执行标的信息校验未通过: layyid=%s updated_keys=%s issues=%s",
                    layyid,
                    ",".join(sorted(updated_keys)) or "-",
                    "；".join(issues[:6]),
                )

        if issues:
            collapsed = "；".join(issues[:8])
            raise RuntimeError(f"HTTP立案完整性校验失败: {collapsed}")

    async def _update_execution_target_info(
        self: Any, *, layyid: str, fyid: str, case_data: dict[str, Any]
    ) -> set[str]:
        reason = str(case_data.get("execution_reason") or "").strip()
        request = str(case_data.get("execution_request") or "").strip()
        amount = str(case_data.get("target_amount") or "").strip()
        target_codes = self._resolve_execution_target_codes(case_data, amount=amount)

        if not reason and not request and not amount and not target_codes:
            return set()

        updated_keys: set[str] = set()

        detail = await self._get(f"/yzw-zxfw-lafw/api/v3/layy/layyxq/{layyid}/0")
        layy = (detail or {}).get("layy") if isinstance(detail, dict) else {}
        layy_dict = layy if isinstance(layy, dict) else {}
        zxyj_source = (detail or {}).get("zxyjs") or (detail or {}).get("zxyj") or []
        zxyj_records = [row for row in zxyj_source if isinstance(row, dict)]
        base_zxyj = dict(zxyj_records[0]) if zxyj_records else {}

        zxyj_payload: dict[str, Any] = {
            "layyId": layyid,
            "fyId": str(self._first_non_empty(base_zxyj, ("fyId", "fyid")) or fyid),
            "jbjg": str(self._first_non_empty(base_zxyj, ("jbjg",)) or fyid),
            "jbjgMc": str(
                self._first_non_empty(base_zxyj, ("jbjgMc",))
                or case_data.get("court_name")
                or self._first_non_empty(layy_dict, ("fymc",))
                or ""
            ),
            "zxyjAh": str(
                self._first_non_empty(base_zxyj, ("zxyjAh",))
                or case_data.get("original_case_number")
                or self._first_non_empty(layy_dict, ("ysajah",))
                or ""
            ),
            "zxyjlb": str(self._first_non_empty(base_zxyj, ("zxyjlb",)) or "1501_11400101-1"),
            "zxyjmc": str(
                self._first_non_empty(base_zxyj, ("zxyjmc",)) or case_data.get("execution_basis_type") or "民商"
            ),
        }
        zxyj_id = str(self._first_non_empty(base_zxyj, ("id", "zxyjid"))).strip()
        if zxyj_id:
            zxyj_payload["id"] = zxyj_id

        if reason:
            zxyj_payload["zxyjzw"] = reason
            updated_keys.add("zxyjzw")
        if request:
            zxyj_payload["zxqq"] = request
            updated_keys.add("zxqq")
        if target_codes:
            zxyj_payload["sqzxbdzl"] = ",".join(target_codes)
            updated_keys.add("sqzxbdzl")
        if amount and EXECUTION_TARGET_CODE_MONEY in target_codes:
            zxyj_payload["sqzxbdje"] = amount
            updated_keys.add("sqzxbdje")

        field_sources = {
            "sqzxbdxw": ("execution_target_behavior", "sqzxbdxw"),
            "sqzxbdccxql": ("execution_target_property_right", "sqzxbdccxql"),
            "sqzxbddc": ("execution_target_movable", "sqzxbddc"),
            "sqzxbdbdc": ("execution_target_immovable", "sqzxbdbdc"),
        }
        for target_field, source_keys in field_sources.items():
            value = ""
            for source_key in source_keys:
                value = str(case_data.get(source_key) or "").strip()
                if value:
                    break
            if not value:
                value = str(base_zxyj.get(target_field) or "").strip()
            if value:
                zxyj_payload[target_field] = value
                updated_keys.add(target_field)

        await self._patch("/yzw-zxfw-lafw/api/v3/zxyj", zxyj_payload)

        jbxx = await self._get_jbxx(layyid)
        if jbxx:
            if reason:
                jbxx["zxyy"] = reason
                updated_keys.add("zxyy")
            if request:
                jbxx["zxqq"] = request
                updated_keys.add("zxqq")
            if target_codes:
                jbxx["sqzxbdzl"] = ",".join(target_codes)
                updated_keys.add("layy.sqzxbdzl")
            if amount and EXECUTION_TARGET_CODE_MONEY in target_codes:
                jbxx["sqzxbdje"] = amount
                jbxx["sqbdje"] = amount
                updated_keys.add("layy.sqzxbdje")
            await self._patch_layy(layyid, jbxx)

        logger.info("执行标的信息更新完成: keys=%s", ",".join(sorted(updated_keys)))
        return updated_keys
