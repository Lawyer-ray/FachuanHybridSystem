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

        # 已有正式代理人（dlr 字段）
        existing_dlr: list[dict[str, Any]] = [
            item for item in (detail or {}).get("dlr") or []
            if isinstance(item, dict) and item.get("id")
        ]
        # 法院自动识别的待补全代理人（dlrs 字段）
        auto_recognized: list[dict[str, Any]] = [
            item for item in (detail or {}).get("dlrs") or []
            if isinstance(item, dict) and item.get("id")
        ]

        logger.info(
            "代理人更新: layyid=%s, bdlrid=%s, 待写入=%d, 已有正式=%d, 自动识别=%d",
            layyid, bdlrid, len(agents), len(existing_dlr), len(auto_recognized),
        )

        # 策略：优先补全自动识别的代理人（按名字匹配），剩下的才新建
        used_auto_ids: set[str] = set()
        for agent in agents:
            if not agent.get("name"):
                continue
            agent_name = str(agent.get("name") or "").strip()

            # 1. 先看是否有自动识别的代理人可以补全
            matched_auto = None
            for auto_item in auto_recognized:
                auto_id = str(auto_item.get("id") or "").strip()
                if auto_id in used_auto_ids:
                    continue
                auto_name = str(auto_item.get("xm") or auto_item.get("name") or "").strip()
                if agent_name and auto_name and agent_name == auto_name:
                    matched_auto = auto_item
                    used_auto_ids.add(auto_id)
                    break

            if matched_auto:
                # 补全自动识别的代理人
                agent_id = str(matched_auto.get("id") or "").strip()
                logger.info("补全自动识别代理人: %s (id=%s)", agent_name, agent_id)
                await self._update_agent(
                    layyid=layyid,
                    fyid=fyid,
                    bdlrid=bdlrid,
                    agent=agent,
                    is_exec=is_exec,
                    agent_id=agent_id,
                    principal_name=principal_name,
                    is_new=False,
                )
            else:
                # 2. 没有匹配的自动识别代理人，检查正式代理人列表
                is_existing = False
                for existing in existing_dlr:
                    existing_name = str(existing.get("xm") or existing.get("name") or "").strip()
                    if agent_name and existing_name and agent_name == existing_name:
                        agent_id = str(existing.get("id") or "").strip()
                        is_existing = True
                        logger.info("更新正式代理人: %s (id=%s)", agent_name, agent_id)
                        break

                if is_existing:
                    await self._update_agent(
                        layyid=layyid,
                        fyid=fyid,
                        bdlrid=bdlrid,
                        agent=agent,
                        is_exec=is_exec,
                        agent_id=agent_id,
                        principal_name=principal_name,
                        is_new=False,
                    )
                else:
                    # 3. 都没有匹配，创建新代理人
                    logger.info("创建新代理人: %s", agent_name)
                    await self._update_agent(
                        layyid=layyid,
                        fyid=fyid,
                        bdlrid=bdlrid,
                        agent=agent,
                        is_exec=is_exec,
                        agent_id=None,
                        principal_name=principal_name,
                        is_new=True,
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
        is_new: bool = False,
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

        if is_new:
            # 新代理人用 POST 创建（PATCH 只能更新已有记录）
            result = await self._post("/yzw-zxfw-lafw/api/v3/layy/dlr", payload)
            logger.info("代理人创建完成: %s, id=%s, 响应=%s", agent["name"], dlr_id, result)
        else:
            # 已有代理人用 PATCH 更新
            result = await self._patch("/yzw-zxfw-lafw/api/v3/layy/dlr", payload)
            logger.info("代理人更新完成: %s, id=%s, 响应=%s", agent["name"], dlr_id, result)
