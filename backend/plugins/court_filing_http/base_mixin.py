from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

from .constants import _BASE, _OSS_BUCKET

logger = logging.getLogger("plugins.court_filing_http")

class BaseApiMixin:
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
        original_filename: str = "",
    ) -> None:
        ext = Path(file_path).suffix
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

        fname = original_filename or Path(file_path).name

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
            files={"file": (fname, file_bytes)},
            timeout=60.0,
        )
        oss_resp.raise_for_status()

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
