from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("plugins.court_filing_http")

class PartyApiMixin:
    async def _add_party(
        self: Any,
        layyid: str,
        fyid: str,
        party: dict[str, Any],
        role: str,
        role_codes: dict[str, str],
        *,
        is_exec: bool = False,
    ) -> str:
        ssdw = role_codes.get(role, role_codes.get("plaintiff", ""))
        client_type = party.get("client_type", "natural")

        if client_type == "natural":
            id_num: str = party.get("id_number", "")
            gender_raw = party.get("gender", "男")
            xb = "1501_GB0001-1" if gender_raw in ("男", "M") else "1501_GB0001-2"
            csrq = ""
            if len(id_num) == 18:
                csrq = f"{id_num[6:10]}-{id_num[10:12]}-{id_num[12:14]}"
            address = party.get("address", "")
            payload: dict[str, Any] = {
                "xm": party["name"],
                "xb": xb,
                "gj": "1501_GB0006-156",
                "cgj": "中国",
                "zjlx": "1501_000015-1",
                "zjhm": id_num,
                "csrq": csrq,
                "nl": "",
                "gzdw": "",
                "mz": "1501_GB0002-01",
                "cmz": "汉族",
                "zy": "",
                "sjhm": party.get("phone", ""),
                "dsrlx": "1501_000011-1",
                "ssdw": ssdw,
                "cdsrlx": "自然人",
                "cxb": gender_raw,
                "czjlx": "居民身份证",
                "layyid": layyid,
                "fyId": fyid,
                "zt": "",
            }
            if is_exec:
                payload["hjszd"] = address
                payload["dz"] = address
            else:
                payload["dz"] = address
        else:
            payload = {
                "dwmc": party["name"],
                "dwzsd": party.get("address", ""),
                "gj": "1501_GB0006-156",
                "cgj": "中国",
                "zzlx": "1501_000031-4",
                "zzhm": party.get("uscc", ""),
                "fddbrxm": party.get("legal_rep", ""),
                "fddbrzw": "",
                "fddbrzjlx": "1501_000015-1",
                "fddbrzjhm": party.get("legal_rep_id_number", ""),
                "fddbrsjhm": party.get("phone", ""),
                "fddbrgddh": party.get("phone", ""),
                "dwxz": "",
                "dsrlx": "1501_000011-2",
                "ssdw": ssdw,
                "cdsrlx": "法人",
                "czzlx": "统一社会信用代码证",
                "cfddbrzjlx": "居民身份证",
                "layyid": layyid,
                "fyId": fyid,
                "zt": "",
            }
            if is_exec:
                payload["zcdq"] = "1501_GB0006-156"
                payload["czcdq"] = "中国"

        dsrid = await self._post("/yzw-zxfw-lafw/api/v3/layy/dsr", payload)
        logger.info("添加当事人: %s → %s", party["name"], dsrid)
        return str(dsrid)

    async def _update_agents(
        self: Any,
        layyid: str,
        fyid: str,
        bdlrid: str,
        agents: list[dict[str, Any]],
        *,
        is_exec: bool = False,
        principal_name: str = "",
    ) -> None:
        detail = await self._get(f"/yzw-zxfw-lafw/api/v3/layy/layyxq/{layyid}/0")
        existing_dlr_ids: list[str] = []
        for item in (detail or {}).get("dlr") or []:
            agent_id = str(item.get("id") or "").strip()
            if agent_id:
                existing_dlr_ids.append(agent_id)

        for idx, agent in enumerate(agents):
            if not agent.get("name"):
                continue
            agent_id = existing_dlr_ids[idx] if idx < len(existing_dlr_ids) else uuid.uuid4().hex
            await self._update_agent(
                layyid=layyid,
                fyid=fyid,
                bdlrid=bdlrid,
                agent=agent,
                is_exec=is_exec,
                agent_id=agent_id,
                principal_name=principal_name,
            )

    async def _update_agent(
        self: Any,
        layyid: str,
        fyid: str,
        bdlrid: str,
        agent: dict[str, Any],
        *,
        is_exec: bool = False,
        agent_id: str | None = None,
        principal_name: str = "",
    ) -> None:
        dlr_id = str(agent_id or "").strip() or uuid.uuid4().hex

        payload: dict[str, Any] = {
            "bdlrid": bdlrid,
            "dlrlx": "1501_000013-1",
            "xm": agent["name"],
            "zjlx": "1501_000015-1",
            "zjhm": agent.get("id_number", ""),
            "zyzh": agent.get("bar_number", ""),
            "zyjg": agent.get("law_firm", ""),
            "sjhm": agent.get("phone", ""),
            "id": dlr_id,
            "layyid": layyid,
            "czjlx": "居民身份证",
            "gj": "1501_GB0006-156",
            "cgj": "中国",
            "sfsqr": "1501_000010-1",
            "noDelete": True,
            "dlrType": "fls",
            "zt": "",
            "edit": True,
            "cdlrlx": "执业律师",
            "fyId": fyid,
            "bdlrMc": principal_name,
        }
        if is_exec:
            payload["dllx"] = "1501_100434-3"
            payload["zsd"] = agent.get("address", "")
            payload["flyz"] = "1501_000010-2"
            payload["cdllx"] = "委托代理"
            payload["cflyz"] = "否"
            payload["sfdzsd"] = "1501_000010-1"
            payload["csfdzsd"] = "是"

        await self._patch("/yzw-zxfw-lafw/api/v3/layy/dlr", payload)
        logger.info("代理人更新完成: %s", agent["name"])
