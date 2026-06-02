from __future__ import annotations

import asyncio
import logging
from typing import Any

from .constants import (
    EXEC_MATERIAL_CLLX,
    EXEC_MATERIAL_CLMC,
    EXEC_PARTY_ROLE_CODES,
    EXECUTION_TARGET_CODE_MONEY,
    MATERIAL_CLLX,
    MATERIAL_CLMC,
    PARTY_ROLE_CODES,
)

logger = logging.getLogger("plugins.court_filing_http")


class FilingFlowMixin:
    async def _patch_case_type_specific(
        self: Any,
        *,
        layyid: str,
        fyid: str,
        court_name: str,
        case_data: dict[str, Any],
        is_exec: bool,
    ) -> None:
        if is_exec:
            original_case_number = case_data.get("original_case_number", "")
            await self._patch(
                "/yzw-zxfw-lafw/api/v3/layy/ysxx",
                {
                    "layyId": layyid,
                    "fyId": fyid,
                    "ysfyid": "",
                    "ysajbh": "",
                    "ysfymc": "",
                    "ysajAjbs": None,
                    "ysajah": original_case_number,
                },
            )
            basis_type = case_data.get("execution_basis_type", "民商")
            await self._patch(
                "/yzw-zxfw-lafw/api/v3/zxyj",
                {
                    "jbjg": fyid,
                    "jbjgMc": court_name,
                    "zxyjAh": original_case_number,
                    "zxyjlb": "1501_11400101-1",
                    "zxyjmc": basis_type,
                    "layyId": layyid,
                    "fyId": fyid,
                },
            )
            return

        cause = case_data.get("cause_of_action", "")
        if cause:
            await self._patch_layy(
                layyid,
                {
                    "laayMz": await self._lookup_cause_code(cause),
                    "laay": cause,
                    "gxhYs": "",
                },
            )

    async def _upload_materials(self: Any, *, layyid: str, fyid: str, case_data: dict[str, Any], is_exec: bool) -> None:
        cllx_map = EXEC_MATERIAL_CLLX if is_exec else MATERIAL_CLLX
        clmc_map = EXEC_MATERIAL_CLMC if is_exec else MATERIAL_CLMC
        slot_id_by_cllx = await self._extract_material_slot_ids(layyid)
        slot_upload_seq: dict[str, int] = {}
        materials: dict[str, list[tuple[str, str]]] = case_data.get("materials", {})
        if materials and not slot_id_by_cllx:
            raise RuntimeError("接口上传前未能解析材料槽位ID")

        tasks = []
        for slot, items in materials.items():
            cllx = cllx_map.get(slot)
            if not cllx:
                logger.info("跳过不在HTTP API映射中的材料槽位: slot=%s", slot)
                continue
            clmc = clmc_map.get(slot, "材料")
            resolved_ssclid = slot_id_by_cllx.get(cllx)
            if not resolved_ssclid:
                raise RuntimeError(f"未找到材料槽位ID: cllx={cllx}, clmc={clmc}")
            for item in items:
                file_path, original_name = item if isinstance(item, tuple) else (item, "")
                slot_upload_seq[cllx] = slot_upload_seq.get(cllx, 0) + 1
                tasks.append(
                    self._upload_material(
                        layyid,
                        fyid,
                        file_path,
                        cllx,
                        clmc,
                        ssclid=resolved_ssclid,
                        xh=slot_upload_seq[cllx],
                        original_filename=original_name,
                    )
                )
        await asyncio.gather(*tasks)

    async def _write_parties_and_agents(
        self: Any, *, layyid: str, fyid: str, case_data: dict[str, Any], is_exec: bool
    ) -> None:
        role_codes = EXEC_PARTY_ROLE_CODES if is_exec else PARTY_ROLE_CODES
        first_plaintiff_dsrid: str | None = None
        for party in case_data.get("plaintiffs", []):
            dsrid = await self._add_party(layyid, fyid, party, "plaintiff", role_codes, is_exec=is_exec)
            if first_plaintiff_dsrid is None:
                first_plaintiff_dsrid = dsrid
        for party in case_data.get("defendants", []):
            await self._add_party(layyid, fyid, party, "defendant", role_codes, is_exec=is_exec)
        for party in case_data.get("third_parties", []):
            await self._add_party(layyid, fyid, party, "third_party", role_codes, is_exec=is_exec)

        agents = [item for item in case_data.get("agents", []) if isinstance(item, dict)]
        if not agents:
            agent = case_data.get("agent")
            if isinstance(agent, dict):
                agents = [agent]
        logger.info(
            "代理人写入条件检查: agents数量=%d, first_plaintiff_dsrid=%s",
            len(agents),
            first_plaintiff_dsrid,
        )
        if not agents:
            logger.warning("代理人数据为空，跳过代理人写入")
        if not first_plaintiff_dsrid:
            logger.warning("first_plaintiff_dsrid 为空，跳过代理人写入")
        if agents and first_plaintiff_dsrid:
            principal_name = str(((case_data.get("plaintiffs") or [{}])[0]).get("name", "") or "").strip()
            await self._update_agents(
                layyid,
                fyid,
                first_plaintiff_dsrid,
                agents,
                is_exec=is_exec,
                principal_name=principal_name,
            )

    async def _finalize_and_validate(
        self: Any,
        *,
        layyid: str,
        case_data: dict[str, Any],
        is_exec: bool,
        execution_target_updated_keys: set[str],
    ) -> None:
        amount = str(case_data.get("target_amount") or "").strip()
        jbxx = await self._get_jbxx(layyid)
        if amount:
            jbxx["sqbdje"] = amount
        if is_exec:
            target_codes = self._resolve_execution_target_codes(case_data, amount=amount)
            if target_codes:
                jbxx["sqzxbdzl"] = ",".join(target_codes)
            if amount and EXECUTION_TARGET_CODE_MONEY in target_codes:
                jbxx["sqzxbdje"] = amount
        await self._patch_layy(layyid, jbxx)

        detail = await self._get(f"/yzw-zxfw-lafw/api/v3/layy/layyxq/{layyid}/0")
        await self._validate_written_payload(
            layyid=layyid,
            case_data=case_data,
            detail=detail if isinstance(detail, dict) else {},
            is_exec=is_exec,
            execution_target_updated_keys=execution_target_updated_keys,
        )
