"""一张网立案 — 纯 HTTP 接口版。

登录由外部传入 token，本模块只负责立案接口调用。
失败时抛出异常，由调用方决定是否回退到 Playwright 版。
"""

from __future__ import annotations

import base64
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("apps.automation.filing_api")

_BASE = "https://zxfw.court.gov.cn/yzw"
_OSS_BUCKET = "https://zxfy2-oss.oss-cn-north-2-gov-1.aliyuncs.com"

# ── 省份代码 ──────────────────────────────────────────────────
PROVINCE_CODES: dict[str, str] = {
    "广东省": "440000",
    "北京市": "110000",
    "上海市": "310000",
    "浙江省": "330000",
    "江苏省": "320000",
    "湖南省": "430000",
    "湖北省": "420000",
    "四川省": "510000",
    "福建省": "350000",
    "山东省": "370000",
    "河南省": "410000",
    "河北省": "130000",
    "陕西省": "610000",
    "重庆市": "500000",
    "天津市": "120000",
}

# ── 案件类型代码 ──────────────────────────────────────────────
CASE_TYPE_CODES: dict[str, str] = {
    "民事一审": "1501_000001-0301",
    "民事二审": "1501_000001-0302",
    "行政一审": "1501_000001-0401",
    "行政二审": "1501_000001-0402",
    "刑事自诉": "1501_000001-0201",
    "国家赔偿": "1501_000001-0510",
    "申请执行": "1501_000001-1002",
}

# ── 当事人诉讼地位（民事一审） ─────────────────────────────────
PARTY_ROLE_CODES: dict[str, str] = {
    "plaintiff": "1501_030109-1",
    "defendant": "1501_030109-2",
    "third_party": "1501_030109-3",
}

# ── 当事人诉讼地位（申请执行） ─────────────────────────────────
EXEC_PARTY_ROLE_CODES: dict[str, str] = {
    "plaintiff": "1501_100225-1",  # 申请执行人
    "defendant": "1501_100225-2",  # 被执行人
}

# ── 材料类型代码（民事一审，槽位索引 → cllx）────────────────────
MATERIAL_CLLX: dict[str, str] = {
    "0": "11800016-2",  # 起诉状
    "1": "11800016-1",  # 当事人身份证明
    "2": "11800016-9",  # 委托代理人委托手续和身份材料
    "3": "11800016-4",  # 证据目录及证据材料
    "4": "11800016-254",  # 送达地址确认书
}
MATERIAL_CLMC: dict[str, str] = {
    "0": "起诉状",
    "1": "当事人身份证明",
    "2": "委托代理人委托手续和身份材料",
    "3": "证据目录及证据材料",
    "4": "送达地址确认书",
}

# ── 材料类型代码（申请执行）────────────────────────────────────
EXEC_MATERIAL_CLLX: dict[str, str] = {
    "0": "11800016-2",  # 执行申请书
    "1": "11800016-8",  # 执行依据文书
    "2": "11800016-9",  # 授权委托书及代理人身份证明
    "3": "11800016-1",  # 申请人身份材料
    "4": "11800016-254",  # 送达地址确认书
}
EXEC_MATERIAL_CLMC: dict[str, str] = {
    "0": "执行申请书",
    "1": "执行依据文书",
    "2": "授权委托书及代理人身份证明",
    "3": "申请人身份材料",
    "4": "送达地址确认书",
}


class CourtZxfwFilingApiService:
    """纯接口版一张网立案服务。"""

    def __init__(self, token: str) -> None:
        self._token = token
        self._client = httpx.Client(
            headers={
                "Authorization": token,
                "Content-Type": "application/json",
                "Origin": "https://zxfw.court.gov.cn",
                "Referer": "https://zxfw.court.gov.cn/zxfw/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
                ),
            },
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CourtZxfwFilingApiService:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── 公开入口 ──────────────────────────────────────────────

    def file_civil_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        """民事一审立案。"""
        return self._file(case_data, "民事一审")

    def file_administrative_case(self, case_data: dict[str, Any]) -> dict[str, Any]:
        """行政一审立案（接口结构与民事一审完全相同，仅 ajlx 不同）。"""
        return self._file(case_data, "行政一审")

    def file_execution(self, case_data: dict[str, Any]) -> dict[str, Any]:
        """申请执行立案。"""
        return self._file(case_data, "申请执行")

    # ── 核心流程 ──────────────────────────────────────────────

    def _file(self, case_data: dict[str, Any], case_type: str) -> dict[str, Any]:
        province = case_data.get("province", "广东省")
        sfid = PROVINCE_CODES.get(province, "440000")
        court_name: str = case_data["court_name"]
        ajlx = CASE_TYPE_CODES[case_type]
        is_exec = case_type == "申请执行"

        # 1. 查法院 ID
        fyid = self._lookup_court(sfid, court_name)
        logger.info("法院ID: %s → %s", court_name, fyid)

        # 2. 创建立案申请，拿 layyid
        layyid = self._create_layy(fyid, ajlx, sfid, is_exec=is_exec)
        logger.info("立案申请ID: %s", layyid)

        if is_exec:
            # 3a. 填原审案号
            original_case_number = case_data.get("original_case_number", "")
            self._patch(
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
            # 3b. 填执行依据
            basis_type = case_data.get("execution_basis_type", "民商")
            self._patch(
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
        else:
            # 3a. 更新案由
            cause = case_data.get("cause_of_action", "")
            if cause:
                self._patch_layy(
                    layyid,
                    {
                        "laayMz": self._lookup_cause_code(cause),
                        "laay": cause,
                        "gxhYs": "",
                    },
                )

        # 4. 上传材料
        cllx_map = EXEC_MATERIAL_CLLX if is_exec else MATERIAL_CLLX
        clmc_map = EXEC_MATERIAL_CLMC if is_exec else MATERIAL_CLMC
        slot_id_by_cllx = self._extract_material_slot_ids(layyid)
        slot_upload_seq: dict[str, int] = {}
        materials: dict[str, list[str]] = case_data.get("materials", {})
        if materials and not slot_id_by_cllx:
            raise RuntimeError("接口上传前未能解析材料槽位ID")
        for slot, paths in materials.items():
            cllx = cllx_map.get(slot, "11800016-2")
            clmc = clmc_map.get(slot, "材料")
            resolved_ssclid = slot_id_by_cllx.get(cllx)
            if not resolved_ssclid:
                raise RuntimeError(f"未找到材料槽位ID: cllx={cllx}, clmc={clmc}")
            for file_path in paths:
                slot_upload_seq[cllx] = slot_upload_seq.get(cllx, 0) + 1
                self._upload_material(
                    layyid,
                    fyid,
                    file_path,
                    cllx,
                    clmc,
                    ssclid=resolved_ssclid,
                    xh=slot_upload_seq[cllx],
                )

        # 5. 添加当事人
        role_codes = EXEC_PARTY_ROLE_CODES if is_exec else PARTY_ROLE_CODES
        first_plaintiff_dsrid: str | None = None
        for party in case_data.get("plaintiffs", []):
            dsrid = self._add_party(layyid, fyid, party, "plaintiff", role_codes, is_exec=is_exec)
            if first_plaintiff_dsrid is None:
                first_plaintiff_dsrid = dsrid
        for party in case_data.get("defendants", []):
            self._add_party(layyid, fyid, party, "defendant", role_codes, is_exec=is_exec)
        for party in case_data.get("third_parties", []):
            self._add_party(layyid, fyid, party, "third_party", role_codes, is_exec=is_exec)

        # 6. 更新代理人（支持多代理律师）
        agents = [item for item in case_data.get("agents", []) if isinstance(item, dict)]
        if not agents:
            agent = case_data.get("agent")
            if isinstance(agent, dict):
                agents = [agent]
        if agents and first_plaintiff_dsrid:
            principal_name = str(((case_data.get("plaintiffs") or [{}])[0]).get("name", "") or "").strip()
            self._update_agents(
                layyid,
                fyid,
                first_plaintiff_dsrid,
                agents,
                is_exec=is_exec,
                principal_name=principal_name,
            )

        # 7. 执行标的信息（执行理由/执行请求）
        if is_exec:
            self._update_execution_target_info(layyid, case_data)

        # 8. 最终 PATCH（带诉讼标的额）
        amount = case_data.get("target_amount", "")
        jbxx = self._get_jbxx(layyid)
        if amount:
            jbxx["sqbdje"] = amount
        self._patch_layy(layyid, jbxx)

        return {"success": True, "layyid": layyid, "message": f"{case_type}接口立案完成（未提交）"}

    # ── 接口方法 ──────────────────────────────────────────────

    def _get(self, path: str, **params: Any) -> Any:
        r = self._client.get(f"{_BASE}{path}", params=params or None)
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 200:
            raise RuntimeError(f"GET {path} 失败: {body.get('message')}")
        return body.get("data")

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        r = self._client.post(f"{_BASE}{path}", json=payload)
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 200:
            raise RuntimeError(f"POST {path} 失败: {body.get('message')} | {payload}")
        return body.get("data")

    def _patch(self, path: str, payload: dict[str, Any]) -> Any:
        r = self._client.patch(f"{_BASE}{path}", json=payload)
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 200:
            raise RuntimeError(f"PATCH {path} 失败: {body.get('message')}")
        return body.get("data")

    def _lookup_court(self, sfid: str, court_name: str) -> str:
        """按法院名称关键词查 fyid。"""
        keyword = re.sub(r"(人民法院|法院)$", "", court_name).strip()
        for fymc_param in (keyword, ""):
            courts = self._get("/yzw-zxfw-lafw/api/v3/pz/fy", sfid=sfid, city="", fymc=fymc_param)
            if isinstance(courts, list):
                for c in courts:
                    if court_name in c.get("fymc", "") or keyword in c.get("fymc", ""):
                        return str(c.get("value") or c.get("fyid") or c.get("id"))
        raise RuntimeError(f"找不到法院: {court_name}")

    def _create_layy(self, fyid: str, ajlx: str, sfid: str, *, is_exec: bool = False) -> str:
        payload: dict[str, Any] = {
            "ajcx": "zx" if is_exec else "sp",
            "ajlx": ajlx,
            "tjcgsqsfqr": "1",
            "fyid": fyid,
            "sqrsf": "11800010-2",
            "ajlb": "zx" if is_exec else "sp",
            "pcSqrLx": "",
            "sqrlx": "11800011-1",
            "sfid": sfid,
            "ftmc": "",
            "sfzscq": "1501_000010-2",
            "sfysla": "1501_000010-2",
        }
        if not is_exec:
            payload["lafs"] = "2"
        data = self._post("/yzw-zxfw-lafw/api/v3/layy", payload)
        return str(data)

    def _get_jbxx(self, layyid: str) -> dict[str, Any]:
        data = self._get(f"/yzw-zxfw-lafw/api/v3/layy/jbxx/{layyid}")
        return dict(data) if isinstance(data, dict) else {}

    def _patch_layy(self, layyid: str, payload: dict[str, Any]) -> None:
        payload["id"] = layyid
        self._patch("/yzw-zxfw-lafw/api/v3/layy", payload)

    def _extract_material_slot_ids(self, layyid: str) -> dict[str, str]:
        """从立案详情中提取材料槽位ID映射：cllx -> ssclid。"""
        detail = self._get(f"/yzw-zxfw-lafw/api/v3/layy/layyxq/{layyid}/0")
        mapping: dict[str, str] = {}
        id_keys = ("ssclid", "ssclId", "id", "clid")
        cllx_keys = ("cllx", "cllxDm", "cllxdm", "cllxId", "cllxid")

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                node_cllx = ""
                for key in cllx_keys:
                    value = node.get(key)
                    if value:
                        node_cllx = str(value).strip()
                        break

                node_id = ""
                for key in id_keys:
                    value = node.get(key)
                    if value:
                        node_id = str(value).strip()
                        break

                if node_cllx and node_id:
                    mapping.setdefault(node_cllx, node_id)

                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(detail)
        logger.info("提取材料槽位映射完成: %d", len(mapping))
        return mapping

    def _lookup_cause_code(self, cause: str) -> str:
        """从案由树查 laayMz（数字代码）。"""
        try:
            tree = self._get("/yzw-zxfw-lafw/api/v1/ay/tree/batch", lbs="0300")
            if isinstance(tree, list):
                for node in tree:
                    if node.get("laay") == cause or node.get("laayMz") == cause:
                        return str(node.get("laayMz", ""))
                    for child in node.get("children") or []:
                        if child.get("laay") == cause:
                            return str(child.get("laayMz", ""))
        except Exception:
            pass
        return ""

    def _upload_material(
        self,
        layyid: str,
        fyid: str,
        file_path: str,
        cllx: str,
        clmc: str,
        *,
        ssclid: str | None = None,
        xh: int = 1,
    ) -> None:
        """获取 OSS 签名 → 上传文件 → 登记附件。"""
        ext = Path(file_path).suffix  # e.g. ".pdf"
        # 1. 拿签名
        sig = self._post(
            "/yzw-zxfw-ajfw/api/v1/file/upload/signature",
            {
                "path": "layy",
                "ext": ext,
                "fydm": fyid,
                "cllx": cllx,
            },
        )
        key: str = sig["storeAs"]
        oss_url: str = sig.get("ossPath", _OSS_BUCKET)
        # 2. 上传到 OSS（multipart/form-data，使用 STS token）
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        form: dict[str, Any] = {
            "key": key,
            "policy": sig["policy"],
            "OSSAccessKeyId": sig["ossaccessKeyId"],
            "success_action_status": "200",
            "Signature": sig["signature"],
            "x-oss-security-token": sig.get("token", ""),
            "Content-Type": f"application/{ext.lstrip('.')}",
        }
        oss_resp = httpx.post(
            oss_url,
            data=form,
            files={"file": (Path(file_path).name, file_bytes)},
            timeout=60.0,
        )
        oss_resp.raise_for_status()

        # 3. 登记附件
        fname = Path(file_path).name
        self._post(
            "/yzw-zxfw-lafw/api/v3/layy/ssclfj",
            {
                "wjbh": key,
                "layyid": layyid,
                "fyId": fyid,
                "wjmc": fname,
                "path": key,
                "ssclid": ssclid or uuid.uuid4().hex,
                "cllx": cllx,
                "clmc": clmc,
                "bccl": None,
                "name": fname,
                "extname": ext.lstrip("."),
                "url": f"{oss_url.rstrip('/')}/{key}",
                "xh": int(xh or 1),
            },
        )
        logger.info("材料上传完成: %s", fname)

    def _add_party(
        self,
        layyid: str,
        fyid: str,
        party: dict[str, Any],
        role: str,
        role_codes: dict[str, str],
        *,
        is_exec: bool = False,
    ) -> str:
        """添加当事人，返回 dsrid。"""
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
                payload["hjszd"] = address  # 申请执行用户籍所在地
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

        dsrid = self._post("/yzw-zxfw-lafw/api/v3/layy/dsr", payload)
        logger.info("添加当事人: %s → %s", party["name"], dsrid)
        return str(dsrid)

    def _update_agents(
        self,
        layyid: str,
        fyid: str,
        bdlrid: str,
        agents: list[dict[str, Any]],
        *,
        is_exec: bool = False,
        principal_name: str = "",
    ) -> None:
        detail = self._get(f"/yzw-zxfw-lafw/api/v3/layy/layyxq/{layyid}/0")
        existing_dlr_ids: list[str] = []
        for item in (detail or {}).get("dlr") or []:
            agent_id = str(item.get("id") or "").strip()
            if agent_id:
                existing_dlr_ids.append(agent_id)

        for idx, agent in enumerate(agents):
            if not agent.get("name"):
                continue
            agent_id = existing_dlr_ids[idx] if idx < len(existing_dlr_ids) else uuid.uuid4().hex
            self._update_agent(
                layyid=layyid,
                fyid=fyid,
                bdlrid=bdlrid,
                agent=agent,
                is_exec=is_exec,
                agent_id=agent_id,
                principal_name=principal_name,
            )

    def _update_execution_target_info(self, layyid: str, case_data: dict[str, Any]) -> None:
        reason = str(case_data.get("execution_reason") or "").strip()
        request = str(case_data.get("execution_request") or "").strip()
        if not reason and not request:
            return

        jbxx = self._get_jbxx(layyid)
        if not jbxx:
            return

        reason_keys = ("zxyy", "zxly")
        request_keys = ("zxqq", "sqzxsx", "zxqs", "zxqqnr")
        updated_keys: set[str] = set()

        def assign_known(keys: tuple[str, ...], value: str) -> None:
            if not value:
                return
            for key in keys:
                if key in jbxx:
                    jbxx[key] = value
                    updated_keys.add(key)
                    return

        assign_known(reason_keys, reason)
        assign_known(request_keys, request)

        # 若后端响应里未给出键，仍尝试使用常见键名补齐
        fallback_added_keys: list[str] = []
        if reason and not any(key in updated_keys for key in reason_keys):
            jbxx["zxyy"] = reason
            updated_keys.add("zxyy")
            fallback_added_keys.append("zxyy")
        if request and not any(key in updated_keys for key in request_keys):
            jbxx["zxqq"] = request
            updated_keys.add("zxqq")
            fallback_added_keys.append("zxqq")

        if not updated_keys:
            return
        try:
            self._patch_layy(layyid, jbxx)
        except Exception:
            if not fallback_added_keys:
                raise
            for key in fallback_added_keys:
                jbxx.pop(key, None)
            self._patch_layy(layyid, jbxx)
        logger.info("执行标的信息更新完成: keys=%s", ",".join(sorted(updated_keys)))

    def _update_agent(
        self,
        layyid: str,
        fyid: str,
        bdlrid: str,
        agent: dict[str, Any],
        *,
        is_exec: bool = False,
        agent_id: str | None = None,
        principal_name: str = "",
    ) -> None:
        """更新代理人信息（绑定到申请执行人/原告）。"""
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

        self._patch("/yzw-zxfw-lafw/api/v3/layy/dlr", payload)
        logger.info("代理人更新完成: %s", agent["name"])
